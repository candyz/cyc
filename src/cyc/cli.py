import argparse
import asyncio
from contextlib import contextmanager
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Dict, Any

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from rich.console import Console

from cyc import __version__
from cyc.agent import (
    AgentLoop,
    PermissionManager,
    PermissionMode,
    ToolRegistry,
    get_default_tools,
    WorkspaceTrustManager,
    build_coding_agent_system_prompt,
    StdioMCPClient,
    MCPDynamicTool,
    SkillManager,
)
from cyc.adapters import SessionAdapters
from cyc.completion import get_completion_script
from cyc.config import Config, init_config_file, load_config
from cyc.providers import create_provider
from cyc.providers.base import BaseProvider
from cyc.session import SessionManager, get_default_context_limit
from cyc.ui import TerminalUI, create_prompt_session

console = Console()
HISTORY_FILE = Path.home() / ".local" / "share" / "cyc" / "history"

class CliApp:
    def __init__(
        self,
        config: Config,
        provider_name: Optional[str] = None,
        model_name: Optional[str] = None,
        mode: str = "agent",
        permission_mode: PermissionMode = PermissionMode.INTERACTIVE,
        session: Optional[SessionManager] = None,
    ):
        self.config = config
        self.provider_name = provider_name or config.default_provider
        self.provider_config = config.get_provider(self.provider_name)
        self.model = model_name or self.provider_config.default_model or config.default_model
        self.provider: BaseProvider = create_provider(self.provider_config)
        max_ctx = getattr(self.provider_config, "max_context_tokens", None)
        compact_thresh = getattr(getattr(config, "agent", None), "compact_threshold", 0.80)
        self.session = session or SessionManager(
            provider=self.provider_name,
            model=self.model,
            mode=mode,
            max_context_tokens=max_ctx,
            compact_threshold=compact_thresh,
        )
        # Ensure session metadata reflects current settings
        self.session.provider = self.provider_name
        self.session.model = self.model
        self.session.mode = mode
        if hasattr(self.session, "compact_threshold"):
            self.session.compact_threshold = compact_thresh

        self.ui = TerminalUI(stream_markdown=config.ui.markdown_render)
        self.cached_models: List[str] = []
        self.multiline_mode: bool = False

        # Agent configuration
        self.mode = mode  # "chat" or "agent"
        self.workspace_path = Path.cwd()
        if not self.session.workspace:
            self.session.workspace = str(self.workspace_path.resolve())
        if not self.session.git_branch:
            try:
                r = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(self.workspace_path), capture_output=True, text=True, timeout=1)
                if r.returncode == 0:
                    self.session.git_branch = r.stdout.strip()
            except Exception:
                pass
        self.trust_manager = WorkspaceTrustManager()
        self.is_workspace_trusted = self.trust_manager.get_trust_status(self.workspace_path)

        # If untrusted/restricted, force read-only permission mode
        effective_perm_mode = permission_mode
        if self.is_workspace_trusted is False:
            effective_perm_mode = PermissionMode.READ_ONLY

        searxng_url = getattr(getattr(self.config, "agent", None), "searxng_url", None)
        self.tool_registry = ToolRegistry(get_default_tools(searxng_url=searxng_url))
        self.permission_manager = PermissionManager(effective_perm_mode)
        self.mcp_clients: List[StdioMCPClient] = []
        default_max_turns = getattr(getattr(self.config, "agent", None), "max_turns", 100)
        self.agent_loop = AgentLoop(
            provider=self.provider,
            model=self.model,
            session=self.session,
            tool_registry=self.tool_registry,
            permission_manager=self.permission_manager,
            ui=self.ui,
            max_turns=default_max_turns,
        )

        if self.mode == "agent" and not self.session.system_prompt:
            self.session.set_system_prompt(build_coding_agent_system_prompt())

    async def init_mcp_servers(self) -> None:
        """Connect to configured MCP servers, discover their tools, and register them."""
        if not getattr(self.config, "mcp_servers", None):
            return

        for s_name, s_cfg in self.config.mcp_servers.items():
            client = StdioMCPClient(
                name=s_name,
                command=s_cfg.command,
                args=s_cfg.args,
                env=s_cfg.env,
                cwd=s_cfg.cwd,
            )
            started = await client.start()
            if started:
                self.mcp_clients.append(client)
                tools_data = await client.list_tools()
                for td in tools_data:
                    mcp_tool = MCPDynamicTool(
                        server_name=s_name,
                        mcp_client=client,
                        tool_data=td,
                    )
                    self.tool_registry.register(mcp_tool)
                if tools_data:
                    console.print(f"[dim green]✓ MCP '{s_name}': registered {len(tools_data)} external tool(s)[/dim green]")
            else:
                console.print(f"[dim yellow]⚠️  MCP server '{s_name}' failed to start or not found.[/dim yellow]")

    async def close_mcp_servers(self) -> None:
        """Gracefully shut down all active MCP client processes."""
        for client in self.mcp_clients:
            try:
                await client.stop()
            except Exception:
                pass
        self.mcp_clients.clear()

    def get_known_models(self) -> List[str]:
        return self.cached_models

    def get_known_providers(self) -> List[str]:
        return list(self.config.providers.keys())

    def get_known_sessions(self, agent: Optional[str] = None) -> List[str]:
        """Collect known session IDs and aliases for tab completion, optionally filtered by agent."""
        items = self.get_known_session_items(agent)
        res = []
        for item in items:
            res.append(item["id"])
            if item.get("title") and item["title"] not in res:
                res.append(item["title"])
        return res

    def get_known_session_items(self, agent: Optional[str] = None) -> List[Dict]:
        """Collect rich session metadata dicts (id, title, preview, msgs, updated_at, agent) for tab completion."""
        items: List[Dict] = []
        try:
            filter_agent = agent.lower() if agent else None
            if not filter_agent or filter_agent in ("all", "cyc"):
                items.append({
                    "id": "LATEST",
                    "title": "Latest Cyc Session",
                    "preview": "Resume most recent Cyc conversation",
                    "message_count": 0,
                    "updated_at": 0,
                    "agent": "cyc",
                })
                for s in SessionManager.list_sessions():
                    sid = s.get("id") or s.get("session_id")
                    if sid:
                        items.append({
                            "id": sid,
                            "title": s.get("title", ""),
                            "preview": s.get("preview", ""),
                            "message_count": s.get("message_count", 0),
                            "updated_at": s.get("updated_at", 0),
                            "agent": "cyc",
                        })
            if not filter_agent or filter_agent in ("all", "agy"):
                for s in SessionAdapters.list_agy_sessions():
                    sid = s.get("id") or s.get("session_id")
                    if sid:
                        items.append({
                            "id": sid,
                            "title": s.get("title", ""),
                            "preview": s.get("preview", ""),
                            "message_count": s.get("message_count", 0),
                            "updated_at": s.get("updated_at", 0),
                            "agent": "agy",
                        })
            if not filter_agent or filter_agent in ("all", "claude"):
                for s in SessionAdapters.list_claude_sessions():
                    sid = s.get("id") or s.get("session_id")
                    if sid:
                        items.append({
                            "id": sid,
                            "title": s.get("title", ""),
                            "preview": s.get("preview", ""),
                            "message_count": s.get("message_count", 0),
                            "updated_at": s.get("updated_at", 0),
                            "agent": "claude",
                        })
            if not filter_agent or filter_agent in ("all", "pi"):
                for s in SessionAdapters.list_pi_sessions():
                    sid = s.get("id") or s.get("session_id")
                    if sid:
                        items.append({
                            "id": sid,
                            "title": s.get("title", ""),
                            "preview": s.get("preview", ""),
                            "message_count": s.get("message_count", 0),
                            "updated_at": s.get("updated_at", 0),
                            "agent": "pi",
                        })
            if not filter_agent or filter_agent in ("all", "opencode"):
                for s in SessionAdapters.list_opencode_sessions():
                    sid = s.get("id") or s.get("session_id")
                    if sid:
                        items.append({
                            "id": sid,
                            "title": s.get("title", ""),
                            "preview": s.get("preview", ""),
                            "message_count": s.get("message_count", 0),
                            "updated_at": s.get("updated_at", 0),
                            "agent": "opencode",
                        })
        except Exception:
            pass
        return items

    async def update_cached_models(self) -> None:
        try:
            models = await self.provider.list_models()
            if self.provider_name.lower() == "openrouter":
                self.cached_models = [m for m in models if m.lower().endswith("free")]
            else:
                self.cached_models = models
        except Exception:
            self.cached_models = []

    def switch_provider(self, provider_name: str, model_name: Optional[str] = None):
        self.provider_config = self.config.get_provider(provider_name)
        self.provider_name = provider_name
        self.provider = create_provider(self.provider_config)
        self.model = model_name or self.provider_config.default_model or self.config.default_model
        self.session.provider = self.provider_name
        self.session.model = self.model
        cfg_tokens = getattr(self.provider_config, "max_context_tokens", None)
        if cfg_tokens:
            self.session.max_context_tokens = cfg_tokens
        else:
            self.session.max_context_tokens = get_default_context_limit(self.provider_name, self.model)
        # Update agent_loop references
        self.agent_loop.provider = self.provider
        self.agent_loop.model = self.model
        console.print(f"[bold green]Switched to provider:[/bold green] {self.provider_name} (model: {self.model})")
        # Trigger background model cache refresh
        asyncio.create_task(self.update_cached_models())

    async def execute_shell_command(self, cmd_line: str) -> None:
        """Execute a local shell command directly via '!command' shortcut."""
        cmd = cmd_line.strip()
        if not cmd:
            console.print("[dim yellow]Usage: !<command> (e.g. !ls -la, !git status, !pwd)[/dim yellow]")
            return

        console.print(f"[dim cyan]▸ Running:[/dim cyan] [bold]{cmd}[/bold]")
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                cwd=str(self.workspace_path),
            )
            try:
                await proc.wait()
            except (asyncio.CancelledError, KeyboardInterrupt):
                try:
                    proc.terminate()
                    try:
                        await asyncio.wait_for(proc.wait(), timeout=2.0)
                    except (asyncio.TimeoutError, Exception):
                        proc.kill()
                        await proc.wait()
                except Exception:
                    pass
                console.print("\n[dim yellow]Command interrupted by user.[/dim yellow]")
        except Exception as e:
            console.print(f"[bold red]Failed to execute command:[/bold red] {e}")

    async def stream_direct_chat(self, prompt: str) -> None:
        """Stream a lightweight, single-turn answer without invoking agent tools."""
        self.session.add_user_message(prompt)
        try:
            with self.fixed_status_bar_scroll_region():
                stream_gen = self.provider.chat_stream(self.session.get_messages(), self.model)
                response_text = await self.ui.stream_response(
                    stream_gen=stream_gen,
                    provider=self.provider_name,
                    model=self.model,
                )
                if response_text:
                    self.session.add_assistant_message(response_text)
        except Exception as e:
            console.print(f"\n[bold red]API Error:[/bold red] {e}\n")

    async def run_single_prompt(self, user_prompt: str) -> None:
        if user_prompt.startswith("?") or user_prompt.startswith("/chat "):
            clean_prompt = user_prompt[1:].strip() if user_prompt.startswith("?") else user_prompt[6:].strip()
            if clean_prompt:
                await self.stream_direct_chat(clean_prompt)
                return

        if self.mode == "agent":
            try:
                await self.agent_loop.run_turn(user_prompt)
            except (KeyboardInterrupt, asyncio.CancelledError):
                pass
            except Exception as e:
                console.print(f"\n[bold red]Agent Error:[/bold red] {e}")
            return

        await self.stream_direct_chat(user_prompt)

    async def handle_slash_command(self, cmd: str) -> bool:
        """Handle slash commands. Return True if command was handled."""
        parts = cmd.strip().split(maxsplit=1)
        action = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        if action in ("/quit", "/exit"):
            console.print("[dim]Goodbye![/dim]")
            sys.exit(0)
        elif action == "/clear":
            self.session.clear()
            if self.mode == "agent":
                self.session.set_system_prompt(build_coding_agent_system_prompt())
            console.print("[bold yellow]Session history cleared.[/bold yellow]")
            return True
        elif action == "/help":
            console.print(r"""[bold cyan]Available Commands:[/bold cyan]
  /help                       Show this help message
  !<command>                  Execute a local shell command directly (e.g. !git status, !ls)
  /mode <mode>                Switch or inspect interaction mode (chat or agent)
  /chat <query>               Quick direct chat question bypassing tools (shortcut: ? <query>)
  /loop <strategy> <turns>    Switch or inspect Agent loop strategy and max turns limit
  /tools                      List registered agent tools (built-in & MCP)
  /skills                     List available skills (builtin, global, workspace)
  /skill <name>               Apply a specialized skill to agent instructions
  /trust <action>             Check or change current workspace trust status (show/allow/deny)
  /sessions <source>          List saved sessions (all, cyc, agy, etc.)
  /sessions manage            Interactive session manager (Resume, Rename, Delete)
  /sessions delete <id>       Delete a local cyc session (alias: /sessions rm)
  /sessions prune             Clean up empty or single-message test sessions
  /sessions rename <id> <t>   Rename a specific cyc session
  /resume <id|title>          Resume a previous session (or latest if omitted)
  /rename <title>             Rename current session with a descriptive title
  /fork <id>                  Fork current session into a new branch
  /sync <agent>               Sync session back to external agent (e.g. /sync agy)
  /models                     List available models for the active provider
  /model <name>               Switch active model (tab-completion supported)
  /provider <name>            Switch active provider (tab-completion supported)
  /system <prompt>            Set or inspect system prompt
  /context <limit>            Inspect or update context window token limit
  /compact <ratio>            Manually compact conversation context (summarize & prune)
  /usage                      Show token usage, subscription tier & rate limits
  /multiline                  Toggle multi-line input mode
  /save <filepath>            Save current conversation to Markdown (.md) or JSON (.json)
  /load <filepath>            Load previous conversation from a JSON file
  /undo                       Undo last turn's changes and conversation
  /clear                      Clear current session history
  /exit or /quit              Exit CLI""")
            return True
        elif action == "/sessions":
            # Support:
            # 1. /sessions delete <id|title> or /sessions rm <id|title>
            # 2. /sessions prune [max_messages] or /sessions clean [max_messages]
            # 3. /sessions rename <id> <new_title>
            # 4. /sessions manage (or -i / --interactive)
            # 5. /sessions [all|cyc|agy|claude|pi|opencode]
            sub_parts = arg.split(maxsplit=2) if arg else []
            sub_cmd = sub_parts[0].lower() if sub_parts else ""

            if sub_cmd in ("delete", "rm"):
                if len(sub_parts) < 2:
                    console.print("[yellow]Usage: /sessions delete <session_id|title>[/yellow]")
                    return True
                target_query = arg[len(sub_parts[0]):].strip()
                # If target is currently active session
                if self.session.session_id == target_query or (self.session.title and self.session.title == target_query):
                    console.print("[bold yellow]Cannot delete currently active session. Switch or create a new session first.[/bold yellow]")
                    return True
                success = SessionManager.delete_session(target_query, sessions_dir=self.session.sessions_dir)
                if success:
                    console.print(f"[bold green]✓ Session successfully deleted:[/bold green] [bold cyan]{target_query}[/bold cyan]")
                else:
                    console.print(f"[bold red]Session not found or could not be deleted:[/bold red] {target_query}")
                return True

            elif sub_cmd in ("prune", "clean"):
                max_msgs = 1
                if len(sub_parts) > 1 and sub_parts[1].isdigit():
                    max_msgs = int(sub_parts[1])
                deleted_count = SessionManager.prune_sessions(max_messages=max_msgs, sessions_dir=self.session.sessions_dir)
                console.print(f"[bold green]✓ Cleaned up {deleted_count} empty / test sessions (messages ≤ {max_msgs}).[/bold green]")
                return True

            elif sub_cmd == "rename":
                if len(sub_parts) < 3:
                    console.print("[yellow]Usage: /sessions rename <session_id> <new_title>[/yellow]")
                    return True
                target_id = sub_parts[1]
                new_title = arg.split(maxsplit=2)[2].strip()
                target_sess = SessionManager.find_session(target_id, sessions_dir=self.session.sessions_dir)
                if target_sess:
                    target_sess.rename(new_title)
                    console.print(f"[bold green]✓ Session {target_id} renamed to:[/bold green] [bold cyan]{new_title}[/bold cyan]")
                else:
                    console.print(f"[bold red]Session not found:[/bold red] {target_id}")
                return True

            elif sub_cmd in ("manage", "-i", "--interactive"):
                # Collect all sessions for interactive management
                sessions = []
                sessions.extend(SessionManager.list_sessions(sessions_dir=self.session.sessions_dir))
                sessions.extend(SessionAdapters.list_agy_sessions())
                sessions.extend(SessionAdapters.list_claude_sessions())
                sessions.extend(SessionAdapters.list_pi_sessions())
                sessions.extend(SessionAdapters.list_opencode_sessions())
                sessions.sort(key=lambda s: s["updated_at"], reverse=True)

                if not sessions:
                    console.print("[yellow]No saved sessions found to manage.[/yellow]")
                    return True

                action_result = await self.ui.interactive_session_picker(
                    sessions,
                    current_workspace=self.workspace_path,
                    current_branch=getattr(self.session, "git_branch", None),
                )
                if not action_result:
                    return True

                act = action_result.get("action")
                sess_meta = action_result.get("session") or {}
                sess_id = sess_meta.get("id") or sess_meta.get("session_id")
                source = (sess_meta.get("agent") or sess_meta.get("source") or "cyc").lower()

                if act == "resume":
                    # Delegate to /resume logic
                    return await self.handle_slash_command(f"/resume {source} {sess_id}")
                elif act == "rename":
                    new_title = action_result.get("new_title") or action_result.get("title")
                    if new_title and sess_id:
                        if source != "cyc":
                            console.print(f"[yellow]Renaming external session '{source}' is not supported yet.[/yellow]")
                        else:
                            target_sess = SessionManager.find_session(sess_id)
                            if target_sess:
                                target_sess.rename(new_title)
                                console.print(f"[bold green]✓ Session {sess_id} renamed to:[/bold green] [bold cyan]{new_title}[/bold cyan]")
                elif act == "delete":
                    if source != "cyc":
                        console.print(f"[yellow]Deleting external session from '{source}' is not supported directly in cyc.[/yellow]")
                    else:
                        if self.session.session_id == sess_id:
                            console.print("[bold yellow]Cannot delete currently active session.[/bold yellow]")
                        else:
                            success = SessionManager.delete_session(sess_id)
                            if success:
                                console.print(f"[bold green]✓ Session successfully deleted:[/bold green] [bold cyan]{sess_id}[/bold cyan]")
                            else:
                                console.print(f"[bold red]Could not delete session:[/bold red] {sess_id}")
                return True

            # Standard listing
            filter_source = arg.lower() if arg else "all"
            sessions = []
            if filter_source in ("all", "cyc"):
                sessions.extend(SessionManager.list_sessions())
            if filter_source in ("all", "agy"):
                sessions.extend(SessionAdapters.list_agy_sessions())
            if filter_source in ("all", "claude"):
                sessions.extend(SessionAdapters.list_claude_sessions())
            if filter_source in ("all", "pi"):
                sessions.extend(SessionAdapters.list_pi_sessions())
            if filter_source in ("all", "opencode"):
                sessions.extend(SessionAdapters.list_opencode_sessions())

            sessions.sort(key=lambda s: s["updated_at"], reverse=True)

            if sessions:
                self.ui.print_sessions_table(sessions)
                console.print("[dim]Use '/sessions manage' for interactive selection (Resume / Rename / Delete).[/dim]")
                console.print("[dim]Use '/resume [agent] <session_id>' (or --resume <id>) to resume or import.[/dim]")
            else:
                console.print(f"[yellow]No saved sessions found for source '{filter_source}'.[/yellow]")
            return True
        elif action == "/resume":
            loaded_session = None
            if not arg:
                # Resume latest cyc session
                loaded_session = SessionManager.get_latest_session()
                if not loaded_session:
                    # Fallback to latest external session if no cyc session
                    agy_list = SessionAdapters.list_agy_sessions()
                    if agy_list:
                        loaded_session = SessionAdapters.import_agy_session(agy_list[0]["id"])
                if not loaded_session:
                    opencode_list = SessionAdapters.list_opencode_sessions()
                    if opencode_list:
                        loaded_session = SessionAdapters.import_opencode_session(opencode_list[0]["id"])
                if not loaded_session:
                    console.print("[yellow]No saved sessions available to resume.[/yellow]")
                    return True
            else:
                parts = arg.split(maxsplit=1)
                agent_names = ("cyc", "agy", "claude", "pi", "opencode")

                if len(parts) == 2 and parts[0].lower() in agent_names:
                    target_agent = parts[0].lower()
                    target_query = parts[1].strip()

                    if target_agent == "cyc":
                        loaded_session = SessionManager.find_session(target_query)
                    elif target_agent == "agy":
                        clean_query = target_query[4:] if target_query.startswith("agy_") else target_query
                        loaded_session = SessionAdapters.import_agy_session(clean_query)
                    elif target_agent == "claude":
                        clean_query = target_query[7:] if target_query.startswith("claude_") else target_query
                        loaded_session = SessionAdapters.import_claude_session(clean_query)
                    elif target_agent == "pi":
                        clean_query = target_query[3:] if target_query.startswith("pi_") else target_query
                        loaded_session = SessionAdapters.import_pi_session(clean_query)
                    elif target_agent == "opencode":
                        clean_query = target_query[9:] if target_query.startswith("opencode_") else target_query
                        loaded_session = SessionAdapters.import_opencode_session(clean_query)

                    if not loaded_session:
                        console.print(f"[bold red]Session not found in {target_agent}:[/bold red] {target_query}")
                        return True
                elif len(parts) == 1 and parts[0].lower() in agent_names:
                    # User specified just the agent name e.g. "/resume agy" -> resume latest from that agent
                    target_agent = parts[0].lower()
                    if target_agent == "cyc":
                        loaded_session = SessionManager.get_latest_session()
                    elif target_agent == "agy":
                        agy_list = SessionAdapters.list_agy_sessions()
                        if agy_list:
                            loaded_session = SessionAdapters.import_agy_session(agy_list[0]["id"])
                    elif target_agent == "claude":
                        claude_list = SessionAdapters.list_claude_sessions()
                        if claude_list:
                            loaded_session = SessionAdapters.import_claude_session(claude_list[0]["id"])
                    elif target_agent == "pi":
                        pi_list = SessionAdapters.list_pi_sessions()
                        if pi_list:
                            loaded_session = SessionAdapters.import_pi_session(pi_list[0]["id"])
                    elif target_agent == "opencode":
                        opencode_list = SessionAdapters.list_opencode_sessions()
                        if opencode_list:
                            loaded_session = SessionAdapters.import_opencode_session(opencode_list[0]["id"])

                    if not loaded_session:
                        console.print(f"[yellow]No saved sessions found for agent '{target_agent}'.[/yellow]")
                        return True
                else:
                    target_query = arg
                    # Default: Check cyc sessions first
                    loaded_session = SessionManager.find_session(target_query)

                    # Check agy if starts with agy_ or matches agy UUID
                    if not loaded_session:
                        clean_query = target_query[4:] if target_query.startswith("agy_") else target_query
                        loaded_session = SessionAdapters.import_agy_session(clean_query)

                    # Check claude if starts with claude_ or matches claude ID
                    if not loaded_session:
                        clean_query = target_query[7:] if target_query.startswith("claude_") else target_query
                        loaded_session = SessionAdapters.import_claude_session(clean_query)

                    # Check pi if starts with pi_ or matches pi ID
                    if not loaded_session:
                        clean_query = target_query[3:] if target_query.startswith("pi_") else target_query
                        loaded_session = SessionAdapters.import_pi_session(clean_query)

                    # Check opencode if starts with opencode_ or matches opencode ID
                    if not loaded_session:
                        clean_query = target_query[9:] if target_query.startswith("opencode_") else target_query
                        loaded_session = SessionAdapters.import_opencode_session(clean_query)

                    if not loaded_session:
                        console.print(f"[bold red]Session not found in cyc, agy, claude, pi, or opencode:[/bold red] {target_query}")
                        return True

            self.session = loaded_session
            # Sync agent loop session
            self.agent_loop.session = self.session
            if self.session.mode and self.session.mode != self.mode:
                self.mode = self.session.mode
            if self.session.provider and self.session.provider in self.config.providers:
                self.switch_provider(self.session.provider, self.session.model)
            elif self.session.model:
                self.model = self.session.model
                self.agent_loop.model = self.model

            console.print(f"[bold green]Resumed session:[/bold green] {self.session.session_id} ([cyan]{len(self.session.messages)} messages[/cyan], mode: [magenta]{self.mode}[/magenta])")
            if self.session.messages:
                self.ui.render_resumed_history(self.session.messages)
            return True
        elif action == "/chat":
            if not arg:
                console.print("[dim yellow]Usage: /chat <query> (or prefix prompt with '?') to ask a quick question without invoking tools.[/dim yellow]")
            else:
                await self.stream_direct_chat(arg)
            return True
        elif action == "/mode":
            if not arg:
                console.print(f"Current mode: [bold {'magenta' if self.mode == 'agent' else 'cyan'}]{self.mode.upper()}[/bold {'magenta' if self.mode == 'agent' else 'cyan'}]")
            else:
                target_mode = arg.lower()
                if target_mode in ("chat", "agent"):
                    self.mode = target_mode
                    if self.mode == "agent":
                        self.session.set_system_prompt(build_coding_agent_system_prompt())
                    else:
                        self.session.set_system_prompt(None)
                    console.print(f"[bold green]Switched mode to:[/bold green] [bold {'magenta' if self.mode == 'agent' else 'cyan'}]{self.mode.upper()}[/bold {'magenta' if self.mode == 'agent' else 'cyan'}]")
                else:
                    console.print("[yellow]Invalid mode. Choose 'chat' or 'agent'.[/yellow]")
            return True
        elif action == "/loop":
            if not arg:
                console.print(f"Current agent loop strategy: [bold green]{self.agent_loop.strategy}[/bold green] (Options: standard, plan, minimal)")
                console.print(f"Current agent loop max turns: [bold green]{self.agent_loop.max_turns}[/bold green]")
            else:
                tokens = arg.split()
                changed_something = False
                for token in tokens:
                    t_lower = token.lower()
                    if t_lower in ("standard", "plan", "minimal"):
                        self.agent_loop.strategy = t_lower
                        console.print(f"[bold green]Switched Agent loop strategy to:[/bold green] [bold cyan]{t_lower}[/bold cyan]")
                        changed_something = True
                    elif token.isdigit():
                        val = int(token)
                        if val > 0:
                            self.agent_loop.max_turns = val
                            console.print(f"[bold green]Updated Agent loop max turns to:[/bold green] [bold cyan]{val}[/bold cyan]")
                            changed_something = True
                        else:
                            console.print("[yellow]Max turns must be greater than 0.[/yellow]")
                    else:
                        console.print(f"[yellow]Unknown loop parameter: '{token}'. Options: standard, plan, minimal, or an integer turns limit.[/yellow]")
                if not changed_something:
                    console.print("[yellow]Usage: /loop [strategy] [max_turns] (e.g. /loop 100, /loop plan 50)[/yellow]")
            return True
        elif action == "/rename":
            if not arg:
                curr_title = self.session.title or "(none)"
                console.print(f"Current session title: [bold cyan]{curr_title}[/bold cyan]")
                console.print("[dim]Usage: /rename <new_title> (or /rename <session_id> <new_title>)[/dim]")
            else:
                parts = arg.split(maxsplit=1)
                # Check if user specified a session ID or title for another session
                if len(parts) == 2 and (parts[0] in [s.get("id") for s in SessionManager.list_sessions()] or (self.session.sessions_dir / f"{parts[0]}.json").exists()):
                    target_id = parts[0]
                    new_title = parts[1]
                    target_sess = SessionManager.find_session(target_id)
                    if target_sess:
                        target_sess.rename(new_title)
                        console.print(f"[bold green]✓ Session {target_id} renamed to:[/bold green] [bold cyan]{new_title}[/bold cyan]")
                    else:
                        console.print(f"[bold red]Session not found:[/bold red] {target_id}")
                else:
                    self.session.rename(arg)
                    console.print(f"[bold green]✓ Current session renamed to:[/bold green] [bold cyan]{self.session.title}[/bold cyan]")
            return True
        elif action == "/fork":
            forked_session = self.session.fork_session(new_id=arg if arg else None)
            self.session = forked_session
            self.agent_loop.session = forked_session
            console.print(f"[bold green]✓ Session forked into new branch:[/bold green] [bold cyan]{self.session.session_id}[/bold cyan] ({len(self.session.messages)} messages copied)")
            return True
        elif action == "/sync":
            target_agent = arg.lower().strip() if arg else None
            result = SessionAdapters.sync_session_back(self.session, target_agent=target_agent)
            if result.get("success"):
                synced_cnt = result.get("synced_count", 0)
                conv_id = result.get("conv_id", "")
                console.print(f"[bold green]✓ {result.get('message')}[/bold green]")
                if synced_cnt > 0:
                    console.print(f"[dim]You can now resume in agy with: [cyan]agy --conversation {conv_id}[/cyan] (or [cyan]agy -c[/cyan])[/dim]")
            else:
                console.print(f"[bold red]Sync failed:[/bold red] {result.get('error', 'Unknown error')}")
            return True
        elif action == "/skills":
            skills = SkillManager.list_skills(self.workspace_path, custom_skills_dirs=self.config.skills_dirs)
            self.ui.print_skills_table(skills)
            return True
        elif action == "/skill":
            if not arg:
                console.print("[yellow]Usage: /skill <name>[/yellow]")
            else:
                skill = SkillManager.get_skill(arg, self.workspace_path, custom_skills_dirs=self.config.skills_dirs)
                if not skill:
                    console.print(f"[bold red]Skill '{arg}' not found.[/bold red] Use '/skills' to list available skills.")
                else:
                    current_prompt = self.session.system_prompt or ""
                    addition = f"\n\n[Skill: {skill['name']}]\n{skill['content']}"
                    self.session.set_system_prompt(current_prompt + addition)
                    console.print(f"[bold green]✓ Loaded skill '{skill['name']}':[/bold green] {skill.get('description', '')}")
            return True
        elif action == "/tools":
            self.ui.print_tools_table(self.tool_registry.all_tools())
            return True
        elif action == "/trust":
            subcmd = arg.lower().strip() if arg else "show"
            if subcmd == "show":
                status = self.trust_manager.get_trust_status(self.workspace_path)
                if status is True:
                    console.print(f"[bold green]Workspace Status:[/bold green] Trusted ({self.workspace_path})")
                elif status is False:
                    console.print(f"[bold yellow]Workspace Status:[/bold yellow] Restricted / Untrusted ({self.workspace_path})")
                else:
                    console.print(f"[bold]Workspace Status:[/bold] Undecided ({self.workspace_path})")
            elif subcmd in ("allow", "trust", "yes", "true"):
                self.trust_manager.set_trust(self.workspace_path, True)
                self.is_workspace_trusted = True
                self.permission_manager.mode = PermissionMode.INTERACTIVE
                console.print(f"[bold green]Workspace trusted:[/bold green] Full agent permissions restored for {self.workspace_path}")
            elif subcmd in ("deny", "restrict", "no", "false"):
                self.trust_manager.set_trust(self.workspace_path, False)
                self.is_workspace_trusted = False
                self.permission_manager.mode = PermissionMode.READ_ONLY
                console.print(f"[bold yellow]Workspace restricted:[/bold yellow] Agent locked to [bold]Read-Only[/bold] mode for {self.workspace_path}")
            else:
                console.print("[yellow]Usage: /trust [show|allow|deny][/yellow]")
            return True
        elif action == "/multiline":
            self.multiline_mode = not self.multiline_mode
            status = "[bold green]ON[/bold green] (Press Esc+Enter to submit)" if self.multiline_mode else "[bold yellow]OFF[/bold yellow] (Press Enter to submit, Alt+Enter for newline)"
            console.print(f"Multi-line mode: {status}")
            return True
        elif action == "/models":
            console.print("[dim]Fetching models...[/dim]")
            try:
                raw_models = await self.provider.list_models()
                if self.provider_name.lower() == "openrouter":
                    show_all = arg.lower() in ("--all", "-a", "all")
                    display_models = raw_models if show_all else [m for m in raw_models if m.lower().endswith("free")]
                    self.cached_models = [m for m in raw_models if m.lower().endswith("free")]
                else:
                    display_models = raw_models
                    self.cached_models = raw_models

                if display_models:
                    self.ui.print_models_table(display_models, self.model, self.provider_name)
                    if self.provider_name.lower() == "openrouter" and not arg.lower() in ("--all", "-a", "all"):
                        console.print("[dim]Tip: Filtered to free models (*free). Use '/models --all' to show all models.[/dim]")
                else:
                    console.print(f"[yellow]No models found or listing not supported by provider '{self.provider_name}'.[/yellow]")
            except Exception as e:
                console.print(f"[bold red]Failed to fetch models:[/bold red] {e}")
            return True
        elif action == "/model":
            if not arg:
                console.print(f"Current model: [bold green]{self.model}[/bold green]")
            else:
                self.model = arg
                self.agent_loop.model = arg
                console.print(f"[bold green]Switched model to:[/bold green] {self.model}")
            return True
        elif action == "/provider":
            if not arg:
                console.print(f"Current provider: [bold green]{self.provider_name}[/bold green]")
                console.print(f"Configured providers: {', '.join(self.config.providers.keys())}")
            else:
                try:
                    self.switch_provider(arg)
                except KeyError as e:
                    console.print(f"[bold red]Error:[/bold red] {e}")
            return True
        elif action == "/system":
            if not arg:
                current = self.session.system_prompt or "None"
                console.print(f"System prompt: [cyan]{current}[/cyan]")
            else:
                self.session.set_system_prompt(arg)
                console.print(f"[bold green]System prompt updated:[/bold green] {arg}")
            return True
        elif action == "/context":
            if arg:
                clean_arg = arg.replace(",", "").replace("_", "").lower()
                multiplier = 1
                if clean_arg.endswith("k"):
                    multiplier = 1_000
                    clean_arg = clean_arg[:-1]
                    val_float = float(clean_arg) if clean_arg.replace(".", "", 1).isdigit() else None
                    new_limit = int(val_float * multiplier) if val_float is not None else None
                elif clean_arg.endswith("m"):
                    multiplier = 1_000_000
                    clean_arg = clean_arg[:-1]
                    val_float = float(clean_arg) if clean_arg.replace(".", "", 1).isdigit() else None
                    new_limit = int(val_float * multiplier) if val_float is not None else None
                else:
                    new_limit = int(clean_arg) if clean_arg.isdigit() else None

                if new_limit and new_limit > 0:
                    self.session.max_context_tokens = new_limit
                    console.print(f"[bold green]Updated context window token limit to:[/bold green] [bold cyan]{new_limit:,}[/bold cyan] tokens")
                else:
                    console.print(f"[yellow]Invalid token limit: '{arg}'. Example: /context 128000, /context 200k, or /context 1m[/yellow]")

            self.ui.print_tokens_stats(
                tokens=self.session.total_estimated_tokens(),
                limit=self.session.max_context_tokens,
                msg_count=len(self.session.messages),
            )
            return True
        elif action == "/compact":
            # Manual compaction command
            target_ratio = 0.50
            if arg:
                clean_arg = arg.replace("%", "").strip()
                try:
                    val = float(clean_arg)
                    if val > 1:
                        target_ratio = val / 100.0
                    elif 0 < val <= 1:
                        target_ratio = val
                except ValueError:
                    pass

            with console.status("[dim cyan]Compacting session context...[/dim cyan]", spinner="dots"):
                res = self.session.compact(target_ratio=target_ratio)

            init_t = res["initial_tokens"]
            fin_t = res["final_tokens"]
            saved_t = res["saved_tokens"]
            pct_down = ((init_t - fin_t) / init_t * 100) if init_t > 0 else 0
            console.print(f"[bold green]✓ Session compacted successfully:[/bold green] {init_t:,} → [bold cyan]{fin_t:,}[/bold cyan] tokens ([dim green]-{saved_t:,} tokens, -{pct_down:.1f}%[/dim green])")
            if res.get("pruned_count", 0) > 0:
                console.print(f"[dim]Summarized and consolidated {res['pruned_count']} earlier messages into context brief.[/dim]")
            return True
        elif action == "/usage":
            provider_info = None
            try:
                provider_info = await self.provider.get_usage_info(self.model)
            except Exception:
                pass
            self.ui.print_usage_stats(
                provider_name=self.provider_name,
                model_name=self.model,
                context_tokens=self.session.total_estimated_tokens(),
                context_limit=self.session.max_context_tokens,
                msg_count=len(self.session.messages),
                prompt_tokens=self.session.total_prompt_tokens,
                completion_tokens=self.session.total_completion_tokens,
                provider_info=provider_info,
            )
            return True
        elif action == "/save":
            if not arg:
                console.print("[yellow]Usage: /save <filepath>[/yellow]")
            else:
                out_path = Path(arg).expanduser()
                if out_path.suffix.lower() == ".json":
                    self.session.save_json(out_path)
                else:
                    self.session.save_markdown(out_path)
                console.print(f"[bold green]Session saved to {out_path}[/bold green]")
            return True
        elif action == "/load":
            if not arg:
                console.print("[yellow]Usage: /load <filepath.json>[/yellow]")
            else:
                in_path = Path(arg).expanduser()
                if not in_path.exists():
                    console.print(f"[bold red]File not found:[/bold red] {in_path}")
                else:
                    try:
                        self.session = SessionManager.load_json(in_path)
                        console.print(f"[bold green]Loaded {len(self.session.messages)} messages from {in_path}[/bold green]")
                        if self.session.messages:
                            self.ui.render_resumed_history(self.session.messages)
                    except Exception as e:
                        console.print(f"[bold red]Failed to load session:[/bold red] {e}")
            return True
        elif action == "/undo":
            success = self.session.undo_turn()
            if not success:
                console.print("[yellow]Nothing to undo (no previous turns in this session).[/yellow]")
                return True

            console.print(f"[bold green]✓ Undid last conversation turn.[/bold green] ({len(self.session.messages)} messages remaining)")

            # If inside a git repository, ask user if they want to discard uncommitted file modifications
            try:
                git_status = subprocess.run(
                    ["git", "status", "--porcelain"],
                    cwd=str(self.workspace_path),
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                if git_status.returncode == 0 and git_status.stdout.strip():
                    console.print("[dim yellow]Detected uncommitted changes in workspace after turn.[/dim yellow]")
                    choice = input("Would you like to discard uncommitted git changes as well? (git restore .) [y/N]: ").strip().lower()
                    if choice in ("y", "yes"):
                        subprocess.run(["git", "restore", "."], cwd=str(self.workspace_path), timeout=5)
                        console.print("[bold green]✓ Workspace changes discarded (git restore .).[/bold green]")
            except Exception:
                pass

            return True
        return False

    def _get_status_toolbar(self) -> HTML:
        """Generate status bar displayed at the bottom of the prompt."""
        mode_badge = f"<b><style bg='ansimagenta' fg='ansiwhite'> AGENT </style></b>" if self.mode == "agent" else f"<b><style bg='ansicyan' fg='ansiwhite'> CHAT </style></b>"
        ml_badge = "<style fg='ansimagenta'>[Multi-line: Esc+Enter]</style>" if self.multiline_mode else "<style fg='ansigray'>[Single-line]</style>"

        if self.is_workspace_trusted is False:
            trust_badge = "<style bg='ansired' fg='ansiwhite'><b> UNTRUSTED (READ-ONLY) </b></style>"
        elif self.is_workspace_trusted is True:
            trust_badge = "<style fg='ansigreen'>[Trusted]</style>"
        else:
            trust_badge = "<style fg='ansiyellow'>[Untrusted]</style>"

        tokens = self.session.total_estimated_tokens()
        limit = self.session.max_context_tokens
        token_str = f"{tokens}/{limit}"
        project_name = self.workspace_path.name or str(self.workspace_path)

        status_text = (
            f" {mode_badge} "
            f"<b>Context:</b> <style fg='ansiyellow'>{token_str}</style> | "
            f"<style fg='ansibrightyellow'>{project_name}</style> | "
            f"<style fg='ansigreen'>{self.provider_name}</style> | "
            f"<style fg='ansicyan'>{self.model}</style> | "
            f"{trust_badge} | "
            f"{ml_badge} "
        )
        return HTML(status_text)

    def _get_status_line_markup(self) -> str:
        mode_badge = "[bold white on magenta] AGENT [/bold white on magenta]" if self.mode == "agent" else "[bold white on cyan] CHAT [/bold white on cyan]"
        ml_badge = "[magenta][Multi-line][/magenta]" if self.multiline_mode else "[dim][Single-line][/dim]"

        if self.is_workspace_trusted is False:
            trust_badge = "[bold white on red] UNTRUSTED (READ-ONLY) [/bold white on red]"
        elif self.is_workspace_trusted is True:
            trust_badge = "[green][Trusted][/green]"
        else:
            trust_badge = "[yellow][Untrusted][/yellow]"

        tokens = self.session.total_estimated_tokens()
        limit = self.session.max_context_tokens
        token_str = f"{tokens}/{limit}"
        project_name = self.workspace_path.name or str(self.workspace_path)

        return (
            f"{mode_badge} "
            f"[bold]Context:[/bold] [yellow]{token_str}[/yellow] | "
            f"[bright_yellow]{project_name}[/bright_yellow] | "
            f"[green]{self.provider_name}[/green] | "
            f"[cyan]{self.model}[/cyan] | "
            f"{trust_badge} | "
            f"{ml_badge}"
        )

    def print_status_bar(self) -> None:
        """Render a standalone status line to terminal (e.g. after long agent turn scrolls)."""
        console.print(self._get_status_line_markup())

    @contextmanager
    def fixed_status_bar_scroll_region(self):
        """Reserve bottom line for fixed status bar and scroll upper region (lines 1..H-1)."""
        is_tty = sys.stdout.isatty() and hasattr(sys.stdout, "write")
        term_size = shutil.get_terminal_size()
        lines, cols = term_size.lines, term_size.columns

        if not is_tty or lines < 4:
            yield
            return

        try:
            from rich.text import Text

            # 1. Restrict scroll region to top lines (1 to lines - 1)
            sys.stdout.write(f"\033[1;{lines-1}r")

            # 2. Render status line markup padded to full width
            markup = " " + self._get_status_line_markup()
            txt = Text.from_markup(markup)
            if txt.cell_len < cols:
                txt.pad_right(cols)
            with console.capture() as cap:
                console.print(txt, end="")
            status_line = cap.get()

            # 3. Draw status line on the last row and position cursor at line lines-1
            sys.stdout.write(f"\033[{lines};1H{status_line}\033[{lines-1};1H\n")
            sys.stdout.flush()

            yield
        finally:
            try:
                # Reset scrolling region to full screen
                sys.stdout.write("\033[r")
                sys.stdout.flush()
            except Exception:
                pass

    async def repl(self) -> None:
        self.ui.print_banner(self.provider_name, self.model, self.multiline_mode, mode=self.mode)
        # Prefetch model list for tab completion
        asyncio.create_task(self.update_cached_models())

        while True:
            prompt_session = create_prompt_session(
                history_file=HISTORY_FILE,
                get_models=self.get_known_models,
                get_providers=self.get_known_providers,
                get_sessions=self.get_known_sessions,
                multiline=self.multiline_mode,
                bottom_toolbar=self._get_status_toolbar,
            )

            prompt_label = "... > " if self.multiline_mode else (f"[{self.mode}] you > " if self.mode != "agent" else "you > ")

            try:
                user_input = await asyncio.to_thread(prompt_session.prompt, prompt_label)
                user_input = user_input.strip()
                if not user_input:
                    continue

                if user_input.startswith("!"):
                    # Shortcut for local shell execution
                    shell_cmd = user_input[1:].strip()
                    await self.execute_shell_command(shell_cmd)
                    continue

                if user_input.startswith("/"):
                    handled = await self.handle_slash_command(user_input)
                    if handled:
                        continue

                # Quick direct chat shortcut: ? <question> bypasses agent tools
                if user_input.startswith("?"):
                    clean_q = user_input[1:].strip()
                    if clean_q:
                        await self.stream_direct_chat(clean_q)
                    continue

                if self.mode == "agent":
                    try:
                        with self.fixed_status_bar_scroll_region():
                            await self.agent_loop.run_turn(user_input)
                    except (KeyboardInterrupt, asyncio.CancelledError):
                        # Graceful interrupt already handled inside agent_loop.run_turn
                        pass
                    except Exception as e:
                        console.print(f"\n[bold red]Agent Error:[/bold red] {e}\n")
                    continue

                await self.stream_direct_chat(user_input)

            except (KeyboardInterrupt, EOFError):
                console.print("\n[dim]Exiting cyc...[/dim]")
                break

def parse_args():
    parser = argparse.ArgumentParser(description="CLI Chat & Autonomous Coding Agent with Local & Cloud LLMs")
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("prompt", nargs="*", help="Direct prompt or piped query (or 'init' to initialize config)")
    parser.add_argument("-p", "--provider", help="Specify provider (e.g. ollama, openrouter, omlx, nvidia, gemini, agy, opencode)")
    parser.add_argument("-m", "--model", help="Specify model name")
    parser.add_argument("-s", "--system", help="Set system prompt")
    parser.add_argument("-c", "--config", help="Custom config path")
    parser.add_argument("--init", action="store_true", help="Generate default configuration file")
    parser.add_argument("-f", "--force", action="store_true", help="Force overwrite existing config during init")
    parser.add_argument("--agent", action="store_true", default=None, help="Enable autonomous Coding Agent mode")
    parser.add_argument("--chat", action="store_true", default=None, help="Force interactive Chat mode")
    parser.add_argument("-y", "--yes", action="store_true", default=None, help="Auto-approve all tool actions without interactive prompt")
    parser.add_argument("--read-only", action="store_true", help="Block all mutation tools (write_file, replace, run_command)")
    parser.add_argument("-r", "--resume", nargs="?", const="__INTERACTIVE__", help="Resume a session (launches interactive Claude Code style session picker if ID omitted)")
    parser.add_argument("--max-turns", type=int, default=None, help="Maximum number of turns for Agent loop (default: 100)")
    parser.add_argument("--sessions", action="store_true", help="List all saved chat & agent sessions and exit")
    parser.add_argument("--trust", action="store_true", default=None, help="Explicitly trust current workspace without prompting")
    parser.add_argument("--no-trust", action="store_true", default=None, help="Explicitly restrict current workspace (force Read-Only mode)")
    parser.add_argument("--completion", nargs="?", const="bash", choices=["bash", "zsh"], help="Generate shell tab-completion script (bash or zsh)")
    parser.add_argument("--web", action="store_true", help="Launch the cyc Web interface server")
    parser.add_argument("--port", type=int, default=None, help="Port for the Web interface (default: 8888)")
    parser.add_argument("--host", type=str, default=None, help="Host address to bind for Web interface (default: 127.0.0.1)")
    parser.add_argument("--token", type=str, default=None, help="Authentication token for Web interface")
    parser.add_argument("--no-open", action="store_true", help="Do not automatically open the browser when starting Web interface")
    parser.add_argument("--bot", action="store_true", help="Launch the cyc Chatbot Gateway (e.g. Telegram)")
    parser.add_argument("--bot-token", type=str, default=None, help="Bot API token (overrides config)")
    return parser.parse_args()

async def async_main():
    args = parse_args()
    config_path = Path(args.config) if args.config else None

    # Handle '--completion'
    if args.completion:
        sys.stdout.write(get_completion_script(args.completion))
        sys.stdout.flush()
        return

    # Handle '--sessions'
    if args.sessions:
        sessions = []
        sessions.extend(SessionManager.list_sessions())
        sessions.extend(SessionAdapters.list_agy_sessions())
        sessions.extend(SessionAdapters.list_claude_sessions())
        sessions.extend(SessionAdapters.list_pi_sessions())
        sessions.extend(SessionAdapters.list_opencode_sessions())
        sessions.sort(key=lambda s: s["updated_at"], reverse=True)

        ui = TerminalUI()
        if sessions:
            ui.print_sessions_table(sessions)
        else:
            console.print("[yellow]No saved sessions found.[/yellow]")
        return

    # Handle 'cyc init' or 'cyc --init'
    is_init_cmd = args.init or (len(args.prompt) == 1 and args.prompt[0].lower() == "init")
    if is_init_cmd:
        try:
            target = init_config_file(config_path, force=args.force)
            console.print(f"[bold green]Configuration initialized successfully:[/bold green] {target}")
            console.print("[dim]You can now edit this file to configure API keys and default models.[/dim]")
            return
        except FileExistsError as e:
            console.print(f"[bold yellow]{e}[/bold yellow]")
            return
        except Exception as e:
            console.print(f"[bold red]Failed to create config:[/bold red] {e}")
            return

    config = load_config(config_path)

    # Handle 'cyc web' or 'cyc --web'
    is_web_cmd = args.web or (len(args.prompt) == 1 and args.prompt[0].lower() == "web")
    if is_web_cmd:
        from cyc.web.server import run_web_server
        await run_web_server(
            config=config,
            host=args.host,
            port=args.port,
            auth_token=args.token,
            open_browser=not args.no_open,
            workspace_path=Path.cwd(),
        )
        return

    # Handle 'cyc bot' or 'cyc --bot'
    is_bot_cmd = args.bot or (len(args.prompt) >= 1 and args.prompt[0].lower() == "bot")
    if is_bot_cmd:
        from cyc.bot.service import TelegramBotService
        bot_service = TelegramBotService(config=config, token=args.bot_token)
        await bot_service.start()
        return

    # Handle '--resume'
    resumed_session: Optional[SessionManager] = None
    if args.resume is not None:
        if args.resume == "__INTERACTIVE__":
            # Collect all sessions across all providers
            sessions = []
            sessions.extend(SessionManager.list_sessions())
            sessions.extend(SessionAdapters.list_agy_sessions())
            sessions.extend(SessionAdapters.list_claude_sessions())
            sessions.extend(SessionAdapters.list_pi_sessions())
            sessions.extend(SessionAdapters.list_opencode_sessions())
            sessions.sort(key=lambda s: s["updated_at"], reverse=True)

            if not sessions:
                console.print("[yellow]No previous sessions found to resume. Starting new session.[/yellow]")
            elif not sys.stdin.isatty():
                # Non-interactive fallback: resume latest
                resumed_session = SessionManager.get_latest_session()
            else:
                curr_branch = None
                try:
                    r = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(Path.cwd()), capture_output=True, text=True, timeout=1)
                    if r.returncode == 0:
                        curr_branch = r.stdout.strip()
                except Exception:
                    pass

                temp_ui = TerminalUI()
                action_res = await temp_ui.interactive_session_picker(
                    sessions,
                    current_workspace=Path.cwd(),
                    current_branch=curr_branch,
                )
                if action_res and action_res.get("action"):
                    act = action_res.get("action")
                    sess_meta = action_res.get("session") or {}
                    target_id = sess_meta.get("id") or sess_meta.get("session_id")
                    target_source = (sess_meta.get("agent") or sess_meta.get("source") or "cyc").lower()

                    if act == "resume":
                        if target_source == "cyc":
                            resumed_session = SessionManager.find_session(target_id)
                        elif target_source == "agy":
                            clean_q = target_id[4:] if target_id.startswith("agy_") else target_id
                            resumed_session = SessionAdapters.import_agy_session(clean_q)
                        elif target_source == "claude":
                            clean_q = target_id[7:] if target_id.startswith("claude_") else target_id
                            resumed_session = SessionAdapters.import_claude_session(clean_q)
                        elif target_source == "pi":
                            clean_q = target_id[3:] if target_id.startswith("pi_") else target_id
                            resumed_session = SessionAdapters.import_pi_session(clean_q)
                        elif target_source == "opencode":
                            clean_q = target_id[9:] if target_id.startswith("opencode_") else target_id
                            resumed_session = SessionAdapters.import_opencode_session(clean_q)
                    elif act == "rename":
                        new_t = action_res.get("new_title") or action_res.get("title")
                        if new_t and target_id:
                            if target_source == "cyc":
                                t_sess = SessionManager.find_session(target_id)
                                if t_sess:
                                    t_sess.rename(new_t)
                                    resumed_session = t_sess
                            else:
                                console.print(f"[yellow]Renaming external session '{target_source}' is not supported yet.[/yellow]")
                    elif act == "delete":
                        if target_source == "cyc":
                            SessionManager.delete_session(target_id)
                            console.print(f"[bold green]✓ Session deleted:[/bold green] {target_id}")
                            return
                        else:
                            console.print(f"[yellow]Deleting external session from '{target_source}' is not supported directly in cyc.[/yellow]")
                            return
                else:
                    # User pressed Esc/Cancel in picker
                    return

        elif args.resume == "LATEST":
            resumed_session = SessionManager.get_latest_session()
            if not resumed_session:
                agy_list = SessionAdapters.list_agy_sessions()
                if agy_list:
                    resumed_session = SessionAdapters.import_agy_session(agy_list[0]["id"])
            if not resumed_session:
                opencode_list = SessionAdapters.list_opencode_sessions()
                if opencode_list:
                    resumed_session = SessionAdapters.import_opencode_session(opencode_list[0]["id"])
            if not resumed_session:
                console.print("[yellow]No previous sessions found to resume. Starting new session.[/yellow]")
        else:
            parts = args.resume.split(maxsplit=1)
            agent_names = ("cyc", "agy", "claude", "pi", "opencode")

            if len(parts) == 2 and parts[0].lower() in agent_names:
                target_agent = parts[0].lower()
                target_query = parts[1].strip()

                if target_agent == "cyc":
                    resumed_session = SessionManager.find_session(target_query)
                elif target_agent == "agy":
                    clean_q = target_query[4:] if target_query.startswith("agy_") else target_query
                    resumed_session = SessionAdapters.import_agy_session(clean_q)
                elif target_agent == "claude":
                    clean_q = target_query[7:] if target_query.startswith("claude_") else target_query
                    resumed_session = SessionAdapters.import_claude_session(clean_q)
                elif target_agent == "pi":
                    clean_q = target_query[3:] if target_query.startswith("pi_") else target_query
                    resumed_session = SessionAdapters.import_pi_session(clean_q)
                elif target_agent == "opencode":
                    clean_q = target_query[9:] if target_query.startswith("opencode_") else target_query
                    resumed_session = SessionAdapters.import_opencode_session(clean_q)
            elif len(parts) == 1 and parts[0].lower() in agent_names:
                target_agent = parts[0].lower()
                if target_agent == "cyc":
                    resumed_session = SessionManager.get_latest_session()
                elif target_agent == "agy":
                    agy_list = SessionAdapters.list_agy_sessions()
                    if agy_list:
                        resumed_session = SessionAdapters.import_agy_session(agy_list[0]["id"])
                elif target_agent == "claude":
                    claude_list = SessionAdapters.list_claude_sessions()
                    if claude_list:
                        resumed_session = SessionAdapters.import_claude_session(claude_list[0]["id"])
                elif target_agent == "pi":
                    pi_list = SessionAdapters.list_pi_sessions()
                    if pi_list:
                        resumed_session = SessionAdapters.import_pi_session(pi_list[0]["id"])
                elif target_agent == "opencode":
                    opencode_list = SessionAdapters.list_opencode_sessions()
                    if opencode_list:
                        resumed_session = SessionAdapters.import_opencode_session(opencode_list[0]["id"])
            else:
                query = args.resume
                # Try cyc
                resumed_session = SessionManager.find_session(query)
                # Try agy
                if not resumed_session:
                    clean_q = query[4:] if query.startswith("agy_") else query
                    resumed_session = SessionAdapters.import_agy_session(clean_q)
                # Try claude
                if not resumed_session:
                    clean_q = query[7:] if query.startswith("claude_") else query
                    resumed_session = SessionAdapters.import_claude_session(clean_q)
                # Try pi
                if not resumed_session:
                    clean_q = query[3:] if query.startswith("pi_") else query
                    resumed_session = SessionAdapters.import_pi_session(clean_q)
                # Try opencode
                if not resumed_session:
                    clean_q = query[9:] if query.startswith("opencode_") else query
                    resumed_session = SessionAdapters.import_opencode_session(clean_q)

            if not resumed_session:
                console.print(f"[bold red]Session not found in cyc, agy, claude, pi, or opencode:[/bold red] {args.resume}. Starting new session.")

    # Determine mode:
    # 1. Command-line flags take highest priority (--agent or --chat)
    # 2. Resumed session mode if available
    # 3. config.agent.default_mode (defaults to "chat")
    configured_default_mode = getattr(getattr(config, "agent", None), "default_mode", "chat")
    if args.agent:
        mode = "agent"
    elif args.chat:
        mode = "chat"
    elif resumed_session and resumed_session.mode:
        mode = resumed_session.mode
    else:
        mode = "agent" if str(configured_default_mode).lower() == "agent" else "chat"

    # Workspace trust evaluation (especially relevant for agent mode or when flags passed)
    trust_mgr = WorkspaceTrustManager()
    configured_default_trust = getattr(getattr(config, "agent", None), "default_trust", None)
    auto_trust_flag = True if args.trust else (False if args.no_trust else configured_default_trust)

    # In agent mode without explicit flags or configured default, prompt if workspace not yet trusted/restricted
    if mode == "agent" and auto_trust_flag is None and trust_mgr.get_trust_status(Path.cwd()) is None:
        if sys.stdin.isatty():
            is_trusted = await trust_mgr.ensure_workspace_trust(Path.cwd())
        else:
            # Non-interactive stdin defaults to restricted for safety
            is_trusted = False
            trust_mgr.set_trust(Path.cwd(), False)
    elif auto_trust_flag is not None:
        trust_mgr.set_trust(Path.cwd(), auto_trust_flag)
        is_trusted = auto_trust_flag
    else:
        is_trusted = trust_mgr.get_trust_status(Path.cwd())

    configured_auto_approve = getattr(getattr(config, "agent", None), "auto_approve", False)
    effective_yes = True if args.yes else (False if getattr(args, "no_yes", False) else configured_auto_approve)

    if args.read_only or is_trusted is False:
        permission_mode = PermissionMode.READ_ONLY
    elif effective_yes:
        permission_mode = PermissionMode.AUTO
    else:
        permission_mode = PermissionMode.INTERACTIVE

    # Determine provider and model
    provider_name = args.provider or (resumed_session.provider if resumed_session else None)
    model_name = args.model or (resumed_session.model if resumed_session else None)

    app = CliApp(
        config,
        provider_name=provider_name,
        model_name=model_name,
        mode=mode,
        permission_mode=permission_mode,
        session=resumed_session,
    )
    if args.max_turns is not None and args.max_turns > 0:
        app.agent_loop.max_turns = args.max_turns

    if args.system:
        app.session.set_system_prompt(args.system)

    if resumed_session:
        console.print(f"[bold green]Resumed session:[/bold green] {resumed_session.session_id} ([cyan]{len(resumed_session.messages)} messages[/cyan], mode: [magenta]{mode}[/magenta])")
        if resumed_session.messages:
            app.ui.render_resumed_history(resumed_session.messages)

    piped_input = ""
    if not sys.stdin.isatty():
        piped_input = sys.stdin.read().strip()

    prompt_arg = " ".join(args.prompt).strip()

    # Initialize MCP servers if configured
    if config.mcp_servers:
        await app.init_mcp_servers()

    try:
        if piped_input or prompt_arg:
            full_prompt = f"{piped_input}\n\n{prompt_arg}".strip() if piped_input and prompt_arg else (piped_input or prompt_arg)
            await app.run_single_prompt(full_prompt)
        else:
            await app.repl()
    finally:
        await app.close_mcp_servers()

def main():
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        sys.exit(0)

if __name__ == "__main__":
    main()
