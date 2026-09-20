import asyncio
import json
import os
import secrets
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import (
    FastAPI,
    HTTPException,
    Header,
    Query,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from cyc import __version__
from cyc.adapters import SessionAdapters
from cyc.agent import (
    AgentLoop,
    PermissionManager,
    PermissionMode,
    ToolRegistry,
    WorkspaceTrustManager,
    get_default_tools,
)
from cyc.config import Config, load_config
from cyc.providers import create_provider
from cyc.session import SessionManager


class QueryRequest(BaseModel):
    prompt: str
    session_id: Optional[str] = None
    mode: Optional[str] = "agent"  # "chat" or "agent"
    provider: Optional[str] = None
    model: Optional[str] = None
    auto_approve: Optional[bool] = None


class SessionCreateRequest(BaseModel):
    provider: Optional[str] = None
    model: Optional[str] = None
    mode: Optional[str] = "agent"
    system_prompt: Optional[str] = None


def create_app(config: Optional[Config] = None, auth_token: Optional[str] = None, workspace_path: Optional[Path] = None) -> FastAPI:
    cfg = config or load_config()
    ws_path = workspace_path or Path.cwd()
    effective_token = auth_token if auth_token is not None else cfg.web.auth_token

    app = FastAPI(title="cyc Web Interface", version=__version__)

    # CORS
    origins = cfg.web.cors_origins or ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Security verification
    def verify_token(token: Optional[str] = None, auth_header: Optional[str] = None) -> bool:
        if not effective_token:
            return True
        if token and secrets.compare_digest(token, effective_token):
            return True
        if auth_header and auth_header.startswith("Bearer "):
            extracted = auth_header[7:].strip()
            if secrets.compare_digest(extracted, effective_token):
                return True
        return False

    @app.middleware("http")
    async def auth_middleware(request: Request, call_next):
        # Exclude static files and root from strict API auth failure so UI can load and prompt for token
        path = request.url.path
        if path.startswith("/api/"):
            token_q = request.query_params.get("token")
            auth_h = request.headers.get("Authorization")
            if not verify_token(token_q, auth_h):
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"detail": "Invalid or missing authentication token"},
                )
        return await call_next(request)

    # ------------------ REST APIs ------------------

    @app.get("/api/status")
    async def get_status():
        trust_mgr = WorkspaceTrustManager()
        is_trusted = trust_mgr.get_trust_status(ws_path)
        prov_model = ""
        try:
            prov_model = cfg.get_provider().default_model
        except Exception:
            pass
        return {
            "version": __version__,
            "workspace": str(ws_path.resolve()),
            "workspace_name": ws_path.resolve().name,
            "workspace_trusted": is_trusted,
            "default_provider": cfg.default_provider,
            "default_model": cfg.default_model or prov_model,
            "providers": list(cfg.providers.keys()),
            "agent_config": {
                "default_mode": cfg.agent.default_mode,
                "auto_approve": cfg.agent.auto_approve,
                "max_turns": cfg.agent.max_turns,
                "compact_threshold": cfg.agent.compact_threshold,
                "searxng_url": cfg.agent.searxng_url,
            },
        }

    @app.get("/api/providers")
    async def get_providers():
        return {
            "default_provider": cfg.default_provider,
            "providers": [
                {
                    "name": name,
                    "type": p.type,
                    "default_model": p.default_model,
                    "base_url": p.base_url,
                }
                for name, p in cfg.providers.items()
            ],
        }

    @app.get("/api/models")
    async def get_models(provider: Optional[str] = None):
        target_provider_name = provider or cfg.default_provider
        try:
            prov_cfg = cfg.get_provider(target_provider_name)
            provider_inst = create_provider(prov_cfg)
            models = await provider_inst.list_models()
            return {"provider": target_provider_name, "models": models}
        except Exception as e:
            return {"provider": target_provider_name, "models": [], "error": str(e)}

    @app.get("/api/sessions")
    async def list_sessions(source: str = "all"):
        sessions = []
        if source in ("all", "cyc"):
            sessions.extend(SessionManager.list_sessions())
        if source in ("all", "agy"):
            sessions.extend(SessionAdapters.list_agy_sessions())
        if source in ("all", "claude"):
            sessions.extend(SessionAdapters.list_claude_sessions())
        if source in ("all", "pi"):
            sessions.extend(SessionAdapters.list_pi_sessions())
        if source in ("all", "opencode"):
            sessions.extend(SessionAdapters.list_opencode_sessions())
        sessions.sort(key=lambda s: s.get("updated_at", 0), reverse=True)
        return {"sessions": sessions}

    @app.get("/api/sessions/{session_id}")
    async def get_session(session_id: str):
        session = SessionManager.find_session(session_id)
        if not session:
            # Check external adapters
            if session_id.startswith("agy_"):
                session = SessionAdapters.import_agy_session(session_id[4:])
            elif session_id.startswith("claude_"):
                session = SessionAdapters.import_claude_session(session_id[7:])
            elif session_id.startswith("pi_"):
                session = SessionAdapters.import_pi_session(session_id[3:])
            elif session_id.startswith("opencode_"):
                session = SessionAdapters.import_opencode_session(session_id[9:])
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        return session.to_dict()

    @app.post("/api/sessions")
    async def create_session(req: SessionCreateRequest):
        prov = req.provider or cfg.default_provider
        mod = req.model or cfg.default_model
        if not mod:
            try:
                mod = cfg.get_provider(prov).default_model
            except Exception:
                pass
        session = SessionManager(
            provider=prov,
            model=mod,
            mode=req.mode or "agent",
            system_prompt=req.system_prompt,
        )
        session.save_json(session.sessions_dir / f"{session.session_id}.json")
        return session.to_dict()

    @app.delete("/api/sessions/{session_id}")
    async def delete_session(session_id: str):
        target_file = Path.home() / ".local" / "share" / "cyc" / "sessions" / f"{session_id}.json"
        if target_file.exists():
            target_file.unlink()
            return {"status": "deleted", "session_id": session_id}
        raise HTTPException(status_code=404, detail="Session file not found")

    @app.get("/api/files")
    async def list_files(path: str = ""):
        """Browse files inside workspace with security path checks."""
        target_path = (ws_path / path).resolve()
        if not str(target_path).startswith(str(ws_path.resolve())):
            raise HTTPException(status_code=403, detail="Access denied: outside workspace root")

        if not target_path.exists():
            raise HTTPException(status_code=404, detail="Path does not exist")

        if target_path.is_file():
            try:
                content = target_path.read_text(encoding="utf-8", errors="replace")
                return {"type": "file", "path": str(target_path.relative_to(ws_path)), "content": content}
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        items = []
        for child in sorted(target_path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            # Skip hidden git and caches
            if child.name in (".git", "__pycache__", ".venv", "node_modules"):
                continue
            items.append({
                "name": child.name,
                "path": str(child.relative_to(ws_path)),
                "is_dir": child.is_dir(),
                "size": child.stat().st_size if child.is_file() else 0,
            })
        return {"type": "directory", "path": str(target_path.relative_to(ws_path)) if target_path != ws_path else "", "items": items}

    # ------------------ WebSocket Agent Engine ------------------

    @app.websocket("/ws/agent")
    async def websocket_agent_endpoint(websocket: WebSocket):
        token = websocket.query_params.get("token")
        if not verify_token(token):
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        await websocket.accept()

        current_task: Optional[asyncio.Task] = None

        try:
            while True:
                raw_text = await websocket.receive_text()
                try:
                    payload = json.loads(raw_text)
                except Exception:
                    continue

                action = payload.get("action")

                if action == "cancel":
                    if current_task and not current_task.done():
                        current_task.cancel()
                        await websocket.send_json({"type": "cancelled", "note": "Cancelled by client request"})
                    continue

                if action == "query":
                    prompt = payload.get("prompt", "")
                    sess_id = payload.get("session_id")
                    mode = payload.get("mode") or cfg.agent.default_mode or "agent"
                    prov_name = payload.get("provider") or cfg.default_provider
                    mod_name = payload.get("model") or cfg.get_provider(prov_name).default_model or cfg.default_model
                    auto_approve = payload.get("auto_approve")
                    if auto_approve is None:
                        auto_approve = cfg.agent.auto_approve

                    # Load or create session
                    session = SessionManager.find_session(sess_id) if sess_id else None
                    if not session:
                        session = SessionManager(
                            session_id=sess_id,
                            provider=prov_name,
                            model=mod_name,
                            mode=mode,
                        )

                    provider_cfg = cfg.get_provider(prov_name)
                    provider_inst = create_provider(provider_cfg)

                    searxng_url = cfg.agent.searxng_url
                    tool_registry = ToolRegistry(get_default_tools(searxng_url=searxng_url))

                    perm_mode = PermissionMode.AUTO if auto_approve else PermissionMode.INTERACTIVE
                    permission_mgr = PermissionManager(perm_mode)

                    async def ws_event_callback(event: Dict[str, Any]):
                        try:
                            await websocket.send_json(event)
                        except Exception:
                            pass

                    agent_loop = AgentLoop(
                        provider=provider_inst,
                        model=mod_name,
                        session=session,
                        tool_registry=tool_registry,
                        permission_manager=permission_mgr,
                        max_turns=cfg.agent.max_turns,
                        strategy="standard",
                        event_callback=ws_event_callback,
                    )

                    async def run_query():
                        try:
                            res = await agent_loop.run_turn(prompt)
                            await websocket.send_json({
                                "type": "turn_complete",
                                "session_id": session.session_id,
                                "result": res,
                            })
                        except asyncio.CancelledError:
                            await websocket.send_json({"type": "cancelled", "note": "Execution cancelled"})
                        except Exception as e:
                            await websocket.send_json({"type": "error", "error": str(e)})

                    current_task = asyncio.create_task(run_query())

        except WebSocketDisconnect:
            if current_task and not current_task.done():
                current_task.cancel()

    # Mount static assets if static dir exists
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

        @app.get("/")
        async def serve_index():
            index_file = static_dir / "index.html"
            if index_file.exists():
                return FileResponse(index_file)
            return JSONResponse({"message": "cyc Web API running. index.html not found."})

    return app
