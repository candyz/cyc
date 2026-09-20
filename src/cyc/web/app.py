import asyncio
import fcntl
import json
import os
import pty
import secrets
import struct
import subprocess
import termios
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
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from cyc import __version__
import shutil
from cyc.adapters import SessionAdapters
from cyc.agent import (
    AgentLoop,
    PermissionManager,
    PermissionMode,
    StdioMCPClient,
    ToolRegistry,
    WorkspaceTrustManager,
    get_default_tools,
)
from cyc.agent.diff import generate_unified_diff
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
    strategy: Optional[str] = "standard"  # "standard", "plan", "minimal"
    max_turns: Optional[int] = None


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

    @app.get("/api/mcp")
    async def get_mcp_servers():
        """List configured MCP servers, executable check, arguments, and topology."""
        servers = []
        for name, mcp_cfg in cfg.mcp_servers.items():
            cmd_resolved = shutil.which(mcp_cfg.command) or mcp_cfg.command
            cmd_exists = bool(shutil.which(mcp_cfg.command) or Path(mcp_cfg.command).exists())
            servers.append({
                "name": name,
                "command": mcp_cfg.command,
                "command_resolved": cmd_resolved,
                "args": mcp_cfg.args,
                "cwd": mcp_cfg.cwd or str(ws_path),
                "is_available": cmd_exists,
                "status": "ready" if cmd_exists else "executable_not_found",
            })
        return {"mcp_servers": servers, "total": len(servers)}

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

    @app.post("/api/sessions/{session_id}/compact")
    async def compact_session(session_id: str, ratio: float = 0.50):
        session = SessionManager.find_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        compact_res = session.compact(target_ratio=ratio)
        return {
            "status": "compacted",
            "session_id": session_id,
            "result": compact_res,
            "session": session.to_dict(),
        }

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

    # ------------------ Server-Sent Events (SSE) Channel ------------------

    @app.post("/api/events/sse")
    async def sse_agent_endpoint(req: QueryRequest, token: Optional[str] = Query(None), authorization: Optional[str] = Header(None)):
        if not verify_token(token, authorization):
            raise HTTPException(status_code=401, detail="Invalid token")

        sess_id = req.session_id
        prov_name = req.provider or cfg.default_provider
        mod_name = req.model or cfg.get_provider(prov_name).default_model or cfg.default_model
        mode = req.mode or cfg.agent.default_mode or "agent"
        auto_approve = req.auto_approve if req.auto_approve is not None else True
        loop_strategy = req.strategy or "standard"
        loop_max_turns = int(req.max_turns or cfg.agent.max_turns)

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

        queue: asyncio.Queue = asyncio.Queue()

        async def sse_event_callback(event: Dict[str, Any]):
            await queue.put(event)

        perm_mode = PermissionMode.AUTO if auto_approve else PermissionMode.READ_ONLY
        permission_mgr = PermissionManager(mode=perm_mode)

        agent_loop = AgentLoop(
            provider=provider_inst,
            model=mod_name,
            session=session,
            tool_registry=tool_registry,
            permission_manager=permission_mgr,
            max_turns=loop_max_turns,
            strategy=loop_strategy,
            event_callback=sse_event_callback,
        )

        async def run_in_background():
            try:
                res = await agent_loop.run_turn(req.prompt)
                await queue.put({
                    "type": "turn_complete",
                    "session_id": session.session_id,
                    "result": res,
                })
            except asyncio.CancelledError:
                await queue.put({"type": "cancelled", "note": "Execution cancelled"})
            except Exception as e:
                await queue.put({"type": "error", "error": str(e)})
            finally:
                await queue.put(None)  # Sentinel to end stream

        asyncio.create_task(run_in_background())

        async def event_generator():
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    # ------------------ WebSocket Agent Engine ------------------

    @app.websocket("/ws/agent")
    async def websocket_agent_endpoint(websocket: WebSocket):
        token = websocket.query_params.get("token")
        if not verify_token(token):
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        await websocket.accept()

        current_task: Optional[asyncio.Task] = None
        pending_approvals: Dict[str, asyncio.Future] = {}

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
                    loop_strategy = payload.get("strategy") or "standard"
                    loop_max_turns = int(payload.get("max_turns") or cfg.agent.max_turns)

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

                    async def web_confirmation_handler(tool, args, prompt_text):
                        approval_id = secrets.token_hex(8)
                        fut = asyncio.get_running_loop().create_future()
                        pending_approvals[approval_id] = fut

                        # Calculate diff preview if mutating files
                        orig_str = None
                        new_str = None
                        if tool.name == "replace_file_content":
                            fp = args.get("path", "")
                            target = args.get("target", "")
                            repl = args.get("replacement", "")
                            orig_file = Path(fp).expanduser()
                            if orig_file.exists() and orig_file.is_file():
                                orig_str = orig_file.read_text(encoding="utf-8", errors="replace")
                                new_str = orig_str.replace(target, repl, 1)
                                diff_text = generate_unified_diff(fp, orig_str, new_str)
                        elif tool.name == "write_file":
                            fp = args.get("path", "")
                            new_str = args.get("content", "")
                            orig_file = Path(fp).expanduser()
                            orig_str = orig_file.read_text(encoding="utf-8", errors="replace") if orig_file.exists() else ""
                            diff_text = generate_unified_diff(fp, orig_str, new_str)

                        await websocket.send_json({
                            "type": "approval_request",
                            "approval_id": approval_id,
                            "tool_name": tool.name,
                            "arguments": args,
                            "diff": diff_text,
                            "orig_text": orig_str,
                            "new_text": new_str,
                            "question": prompt_text or f"Allow '{tool.name}' to execute?",
                        })

                        try:
                            approved = await fut
                            return bool(approved)
                        finally:
                            pending_approvals.pop(approval_id, None)

                    perm_mode = PermissionMode.AUTO if auto_approve else PermissionMode.INTERACTIVE
                    permission_mgr = PermissionManager(
                        mode=perm_mode,
                        confirmation_handler=web_confirmation_handler if not auto_approve else None,
                    )

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
                        max_turns=loop_max_turns,
                        strategy=loop_strategy,
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

                elif action in ("approve", "deny"):
                    approval_id = payload.get("approval_id")
                    if approval_id and approval_id in pending_approvals:
                        fut = pending_approvals[approval_id]
                        if not fut.done():
                            fut.set_result(action == "approve")

        except WebSocketDisconnect:
            if current_task and not current_task.done():
                current_task.cancel()

    # ------------------ WebSocket Web Terminal (PTY Bridge) ------------------

    @app.websocket("/ws/terminal")
    async def websocket_terminal_endpoint(websocket: WebSocket):
        token = websocket.query_params.get("token")
        if not verify_token(token):
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        if not cfg.web.enable_terminal:
            await websocket.close(code=status.WS_1003_UNSUPPORTED_DATA, reason="Terminal disabled in config")
            return

        await websocket.accept()

        master_fd, slave_fd = pty.openpty()
        shell = os.environ.get("SHELL", "/bin/bash")
        proc = subprocess.Popen(
            [shell],
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            cwd=str(ws_path),
            env=os.environ.copy(),
            close_fds=True,
            preexec_fn=os.setsid,
        )
        os.close(slave_fd)

        # Set master_fd non-blocking
        flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
        fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

        loop = asyncio.get_running_loop()
        stop_event = asyncio.Event()

        # Task 1: Read from PTY master_fd -> send to WebSocket
        async def pty_reader():
            while not stop_event.is_set():
                try:
                    await asyncio.sleep(0.01)
                    data = os.read(master_fd, 4096)
                    if data:
                        await websocket.send_text(data.decode("utf-8", errors="replace"))
                except BlockingIOError:
                    await asyncio.sleep(0.02)
                except Exception:
                    break

        reader_task = asyncio.create_task(pty_reader())

        # Task 2: Receive from WebSocket -> write to PTY master_fd
        try:
            while not stop_event.is_set():
                msg_text = await websocket.receive_text()
                try:
                    msg_obj = json.loads(msg_text)
                    msg_type = msg_obj.get("type")
                    if msg_type == "input":
                        data_to_write = msg_obj.get("data", "").encode("utf-8")
                        os.write(master_fd, data_to_write)
                    elif msg_type == "resize":
                        cols = int(msg_obj.get("cols", 80))
                        rows = int(msg_obj.get("rows", 24))
                        winsize = struct.pack("HHHH", rows, cols, 0, 0)
                        fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)
                except json.JSONDecodeError:
                    # Raw input fallback
                    os.write(master_fd, msg_text.encode("utf-8"))
        except (WebSocketDisconnect, asyncio.CancelledError):
            pass
        finally:
            stop_event.set()
            reader_task.cancel()
            try:
                os.close(master_fd)
            except Exception:
                pass
            try:
                proc.terminate()
                proc.wait(timeout=1.0)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

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
