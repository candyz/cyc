import asyncio
import sys
from pathlib import Path
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional

from prompt_toolkit import PromptSession
from prompt_toolkit.application import Application
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.completion import CompleteEvent, Completer, Completion, PathCompleter
from prompt_toolkit.document import Document
from prompt_toolkit.formatted_text import HTML, AnyFormattedText, to_formatted_text
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout, HSplit, VSplit, Window
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import Box, Frame, Label
from rich.box import ROUNDED
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.theme import Theme

from cyc import __version__

custom_theme = Theme({
    "info": "dim cyan",
    "warning": "yellow",
    "error": "bold red",
    "success": "bold green",
})

console = Console(theme=custom_theme)

def fit_width(text: str, target_width: int) -> str:
    """Pad or truncate string so that its terminal display width equals target_width (supports CJK wide chars)."""
    try:
        import wcwidth
        def char_w(c: str) -> int:
            w = wcwidth.wcwidth(c)
            return w if w > 0 else 0
    except ImportError:
        def char_w(c: str) -> int:
            return 1

    total_w = sum(char_w(c) for c in text)
    if total_w == target_width:
        return text
    elif total_w < target_width:
        return text + " " * (target_width - total_w)
    else:
        res = []
        cur_w = 0
        limit = max(0, target_width - 3)
        for c in text:
            cw = char_w(c)
            if cur_w + cw > limit:
                break
            res.append(c)
            cur_w += cw
        truncated = "".join(res) + "..."
        cur_w += 3
        if cur_w < target_width:
            truncated += " " * (target_width - cur_w)
        return truncated

class CommandCompleter(Completer):
    """Dynamic completer for slash commands, models, providers, and filepaths."""
    def __init__(
        self,
        get_models: Callable[[], List[str]],
        get_providers: Callable[[], List[str]],
        get_sessions: Optional[Callable[[Optional[str]], List[str]]] = None,
    ):
        self.get_models = get_models
        self.get_providers = get_providers
        self._get_sessions_fn = get_sessions
        self.path_completer = PathCompleter(expanduser=True)
        self.commands = [
            "/help",
            "/mode",
            "/chat",
            "/loop",
            "/tools",
            "/skills",
            "/skill",
            "/trust",
            "/sessions",
            "/resume",
            "/rename",
            "/fork",
            "/sync",
            "/models",
            "/model",
            "/provider",
            "/system",
            "/context",
            "/compact",
            "/usage",
            "/multiline",
            "/save",
            "/load",
            "/undo",
            "/update",
            "/clear",
            "/exit",
            "/quit",
        ]

    def get_sessions(self, agent: Optional[str] = None) -> List[Any]:
        if not self._get_sessions_fn:
            return []
        import inspect
        sig = inspect.signature(self._get_sessions_fn)
        if len(sig.parameters) >= 1:
            return self._get_sessions_fn(agent)
        return self._get_sessions_fn()

    def get_completions(self, document: Document, complete_event: CompleteEvent):
        text_before_cursor = document.text_before_cursor
        stripped = text_before_cursor.strip()

        # If typing the command itself
        if not " " in text_before_cursor:
            for cmd in self.commands:
                if cmd.startswith(stripped):
                    yield Completion(cmd, start_position=-len(stripped))
            return

        # Subcommand arguments completion
        parts = text_before_cursor.split(maxsplit=1)
        cmd = parts[0].lower()
        arg_prefix = parts[1] if len(parts) > 1 else ""

        if cmd == "/mode":
            for mode in ("chat", "agent"):
                if mode.startswith(arg_prefix.lower()):
                    yield Completion(mode, start_position=-len(arg_prefix))
        elif cmd == "/loop":
            for strat in ("standard", "plan", "minimal"):
                if strat.startswith(arg_prefix.lower()):
                    yield Completion(strat, start_position=-len(arg_prefix))
        elif cmd == "/skill":
            try:
                from cyc.agent.skills import SkillManager
                for s in SkillManager.list_skills():
                    name = s["name"]
                    if name.startswith(arg_prefix.lower()):
                        yield Completion(name, start_position=-len(arg_prefix))
            except Exception:
                pass
        elif cmd == "/sync":
            for opt in ("agy", "claude", "pi", "opencode"):
                if opt.startswith(arg_prefix.lower()):
                    yield Completion(opt, start_position=-len(arg_prefix))
        elif cmd == "/trust":
            for opt in ("show", "allow", "deny"):
                if opt.startswith(arg_prefix.lower()):
                    yield Completion(opt, start_position=-len(arg_prefix))
        elif cmd == "/model":
            for m in self.get_models():
                if m.lower().startswith(arg_prefix.lower()):
                    yield Completion(m, start_position=-len(arg_prefix))
        elif cmd == "/provider":
            for p in self.get_providers():
                if p.lower().startswith(arg_prefix.lower()):
                    yield Completion(p, start_position=-len(arg_prefix))
        elif cmd == "/sessions":
            # Tab completion for sources and subcommands:
            options = ["all", "cyc", "agy", "claude", "pi", "opencode", "manage", "delete", "rm", "prune", "clean", "rename"]
            for opt in options:
                if opt.startswith(arg_prefix.lower()):
                    yield Completion(opt, start_position=-len(arg_prefix))
        elif cmd == "/resume":
            if self.get_sessions:
                # Check if user has typed an agent prefix, e.g. "/resume agy "
                resume_parts = arg_prefix.split(maxsplit=1)
                agent_names = ["cyc", "agy", "claude", "pi", "opencode"]

                def _format_item_meta(item: Any) -> str:
                    if not isinstance(item, dict):
                        return ""
                    title = item.get("title", "")
                    preview = item.get("preview", "")
                    msgs = item.get("message_count", 0)
                    parts = []
                    if title:
                        parts.append(title)
                    elif preview:
                        parts.append(preview[:40])
                    if msgs:
                        parts.append(f"{msgs} msgs")
                    return f" · ".join(parts) if parts else ""

                def _yield_session_completions(items: List[Any], query: str):
                    query_lower = query.lower()
                    seen = set()
                    for it in items:
                        if isinstance(it, dict):
                            sid = it.get("id") or it.get("session_id", "")
                            title = it.get("title", "")
                            meta = _format_item_meta(it)
                            # 1. Match session id
                            if sid and sid.lower().startswith(query_lower) and sid not in seen:
                                seen.add(sid)
                                yield Completion(sid, start_position=-len(query), display_meta=meta)
                            # 2. Match session title as alias
                            if title and title.lower().startswith(query_lower) and title not in seen:
                                seen.add(title)
                                yield Completion(title, start_position=-len(query), display_meta=f"[ID: {sid[:12]}] {meta}")
                        elif isinstance(it, str):
                            if it.lower().startswith(query_lower) and it not in seen:
                                seen.add(it)
                                yield Completion(it, start_position=-len(query))

                if not resume_parts:
                    # User typed "/resume " with no text yet
                    for an in agent_names:
                        yield Completion(an, start_position=0, display_meta="Filter agent sessions")
                    yield from _yield_session_completions(self.get_sessions(None), "")
                elif len(resume_parts) == 1 and not arg_prefix.endswith(" "):
                    # Still typing the first argument: could be an agent name or a session ID / LATEST
                    first_tok = resume_parts[0].lower()
                    # First yield matching agent names
                    for an in agent_names:
                        if an.startswith(first_tok):
                            yield Completion(an, start_position=-len(first_tok), display_meta="Filter agent sessions")
                    # Also yield matching session IDs directly
                    yield from _yield_session_completions(self.get_sessions(None), first_tok)
                else:
                    # User specified first argument and pressed space, or is typing session id for that agent
                    target_agent = resume_parts[0].lower()
                    session_query = resume_parts[1] if len(resume_parts) > 1 else ""

                    if target_agent in agent_names:
                        filter_agent = None if target_agent == "all" else target_agent
                        yield from _yield_session_completions(self.get_sessions(filter_agent), session_query)
                    else:
                        # First argument was not a recognized agent name, fallback to all sessions
                        yield from _yield_session_completions(self.get_sessions(None), arg_prefix)
        elif cmd in ("/save", "/load"):
            # Delegate to PathCompleter with modified document
            sub_doc = Document(arg_prefix, cursor_position=len(arg_prefix))
            for c in self.path_completer.get_completions(sub_doc, complete_event):
                yield c

class TerminalUI:
    def __init__(self, stream_markdown: bool = True):
        self.stream_markdown = stream_markdown
        self.console = console

    def print_banner(self, provider: str, model: str, multiline: bool = False, mode: str = "chat"):
        mode_label = "[bold magenta]🤖 Coding Agent Mode[/bold magenta]" if mode == "agent" else "[dim]💬 Chat Mode[/dim]"
        ml_label = "[magenta]Multi-line[/magenta]" if multiline else "[dim]Single-line[/dim]"
        title = f"[bold green]cyc[/bold green] [dim]v{__version__}[/dim]"
        body = (
            f"Provider: [bold cyan]{provider}[/bold cyan]  |  Model: [bold cyan]{model}[/bold cyan]  |  {mode_label}  |  {ml_label}\n"
            f"[dim]Commands: /help, /mode <chat|agent>, /tools, /sessions, /resume, /models, /model <name>, /provider <name>, /exit[/dim]"
        )
        self.console.print(Panel(body, title=title, border_style="cyan" if mode == "chat" else "magenta", box=ROUNDED))

    def render_resumed_history(self, messages: List[Dict[str, Any]], max_messages: int = 10) -> None:
        """Render previous conversation context when resuming a session so user can inspect past context."""
        if not messages:
            return

        total_msgs = len(messages)
        # Determine slice to display: if history is long, show the last max_messages with a note
        if total_msgs > max_messages:
            displayed = messages[-max_messages:]
            skipped = total_msgs - max_messages
            self.console.print(f"\n[dim]─── Showing last {max_messages} of {total_msgs} messages in history ({skipped} earlier messages hidden) ───[/dim]\n")
        else:
            displayed = messages
            self.console.print(f"\n[dim]─── Session History Context ({total_msgs} message{'s' if total_msgs > 1 else ''}) ───[/dim]\n")

        for msg in displayed:
            role = msg.get("role", "unknown")
            content = msg.get("content") or ""

            if role == "user":
                self.console.print(f"[bold cyan]User:[/bold cyan]\n{content.strip()}\n")
            elif role == "assistant":
                tool_calls = msg.get("tool_calls") or []
                if content:
                    self.console.print(f"[bold green]Assistant:[/bold green]")
                    self.render_formatted_response(content.strip())
                    self.console.print()
                if tool_calls:
                    for tc in tool_calls:
                        func_info = tc.get("function", {})
                        tc_name = func_info.get("name", "tool")
                        tc_args = func_info.get("arguments", "")
                        self.console.print(f"  [dim cyan]⚙ Tool Call: {tc_name}[/dim cyan] [dim]{tc_args}[/dim]")
                    self.console.print()
            elif role == "tool":
                t_name = msg.get("name", "tool")
                lines = content.strip().splitlines()
                preview = lines[0] if lines else ""
                if len(preview) > 100:
                    preview = preview[:97] + "..."
                if len(lines) > 1:
                    preview += f" [dim]({len(lines)} lines)[/dim]"
                self.console.print(f"  [dim green]✓ Observation ({t_name}): {preview}[/dim green]\n")
            elif role == "system":
                preview = content.strip().splitlines()[0] if content.strip() else ""
                if len(preview) > 80:
                    preview = preview[:77] + "..."
                self.console.print(f"[dim]System: {preview}[/dim]\n")

        self.console.print("[dim]────────────────────────────────────────────────────────────[/dim]\n")

    def print_sessions_table(self, sessions: List[Dict]):
        table = Table(title=f"Chat & Agent Sessions ({len(sessions)})", box=ROUNDED)
        table.add_column("Agent", style="bold yellow", justify="center", no_wrap=True)
        table.add_column("Session ID", style="bold cyan", min_width=18, overflow="fold")
        table.add_column("Title / Name", style="bold white", overflow="fold")
        table.add_column("Mode", justify="center", no_wrap=True)
        table.add_column("Provider / Model", style="green", overflow="ellipsis")
        table.add_column("Msgs", justify="right", no_wrap=True)
        table.add_column("Updated", style="dim", no_wrap=True)
        table.add_column("Preview", style="dim", max_width=30, overflow="ellipsis")

        import datetime
        for s in sessions:
            m_time = datetime.datetime.fromtimestamp(s["updated_at"]).strftime("%m-%d %H:%M")
            mode_badge = "[magenta]AGENT[/magenta]" if s.get("mode") == "agent" else "[cyan]CHAT[/cyan]"
            prov = s.get('provider') or '-'
            mod = s.get('model') or '-'
            prov_model = f"{prov}/{mod}"
            agent_source = s.get("agent", "cyc").upper()
            if agent_source == "AGY":
                agent_col = "[bold cyan]AGY[/bold cyan]"
            elif agent_source == "CLAUDE":
                agent_col = "[bold magenta]CLAUDE[/bold magenta]"
            elif agent_source == "PI":
                agent_col = "[bold yellow]PI[/bold yellow]"
            elif agent_source == "OPENCODE":
                agent_col = "[bold blue]OPENCODE[/bold blue]"
            else:
                agent_col = "[bold green]CYC[/bold green]"

            title_text = s.get("title") or "-"
            sid = s.get("id") or s.get("session_id", "-")
            table.add_row(
                agent_col,
                sid,
                title_text,
                mode_badge,
                prov_model,
                str(s.get("message_count", 0)),
                m_time,
                s.get("preview", ""),
            )
        self.console.print(table)

    async def interactive_session_picker(
        self,
        sessions: List[Dict],
        current_workspace: Optional[Path] = None,
        current_branch: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Claude Code style interactive Session Browser with real-time search and rich hotkeys.

        Features:
        - Search bar with live query filtering
        - Space: toggle preview drawer
        - Ctrl+R: rename session
        - Ctrl+D: delete session
        - Ctrl+A: show all sessions (across all workspaces/branches)
        - Ctrl+B: filter to current git branch only
        - Ctrl+P: filter to current project/workspace only
        - Up/Down / PageUp/PageDown: navigation
        - Enter: resume selected session
        - Esc / Ctrl+C: cancel
        """
        if not sessions:
            self.console.print("[yellow]No sessions available to manage.[/yellow]")
            return None

        # Check non-interactive terminal
        if not sys.stdin.isatty():
            self.console.print("[yellow]Interactive session picker requires a TTY terminal.[/yellow]")
            return None

        from prompt_toolkit.shortcuts import input_dialog, yes_no_dialog

        cwd_path = str((current_workspace or Path.cwd()).resolve())
        curr_branch = current_branch or ""

        # Filter state
        filter_mode = "all"  # "all", "branch", "project"
        selected_index = 0
        show_preview = False

        search_buf = Buffer()

        def get_filtered_sessions() -> List[Dict]:
            query = search_buf.text.strip().lower()
            filtered = []
            for s in sessions:
                # Filter by branch / project if requested
                s_branch = s.get("git_branch", "")
                s_ws = s.get("workspace", "")

                if filter_mode == "branch":
                    if curr_branch and s_branch != curr_branch:
                        continue
                elif filter_mode == "project":
                    if cwd_path and s_ws != cwd_path:
                        continue

                if not query:
                    filtered.append(s)
                    continue

                # Match search query against session ID, title, agent, preview, workspace, git_branch
                sid = (s.get("id") or s.get("session_id") or "").lower()
                title = (s.get("title") or "").lower()
                agent = (s.get("agent") or "").lower()
                preview = (s.get("preview") or "").lower()
                ws_str = (s.get("workspace") or "").lower()
                br_str = (s.get("git_branch") or "").lower()

                if (
                    query in sid
                    or query in title
                    or query in agent
                    or query in preview
                    or query in ws_str
                    or query in br_str
                ):
                    filtered.append(s)
            return filtered

        kb = KeyBindings()
        result_action: Dict[str, Any] = {"action": None}

        @kb.add("escape")
        def _on_escape(event):
            event.app.exit(result=None)

        @kb.add("c-c")
        def _on_ctrl_c(event):
            event.app.exit(result=None)

        @kb.add("up")
        def _on_up(event):
            nonlocal selected_index
            filtered = get_filtered_sessions()
            if filtered:
                selected_index = (selected_index - 1) % len(filtered)
            event.app.invalidate()

        @kb.add("down")
        def _on_down(event):
            nonlocal selected_index
            filtered = get_filtered_sessions()
            if filtered:
                selected_index = (selected_index + 1) % len(filtered)
            event.app.invalidate()

        @kb.add("pageup")
        def _on_pageup(event):
            nonlocal selected_index
            filtered = get_filtered_sessions()
            if filtered:
                selected_index = max(0, selected_index - 8)
            event.app.invalidate()

        @kb.add("pagedown")
        def _on_pagedown(event):
            nonlocal selected_index
            filtered = get_filtered_sessions()
            if filtered:
                selected_index = min(len(filtered) - 1, selected_index + 8)
            event.app.invalidate()

        @kb.add("c-a")
        def _on_ctrl_a(event):
            nonlocal filter_mode, selected_index
            filter_mode = "all"
            selected_index = 0
            event.app.invalidate()

        @kb.add("c-b")
        def _on_ctrl_b(event):
            nonlocal filter_mode, selected_index
            filter_mode = "branch" if filter_mode != "branch" else "all"
            selected_index = 0
            event.app.invalidate()

        @kb.add("c-p")
        def _on_ctrl_p(event):
            nonlocal filter_mode, selected_index
            filter_mode = "project" if filter_mode != "project" else "all"
            selected_index = 0
            event.app.invalidate()

        @kb.add("space")
        def _on_space(event):
            nonlocal show_preview
            # If search buffer is empty or user is navigating, space toggles preview
            if not search_buf.text:
                show_preview = not show_preview
                event.app.invalidate()
            else:
                # When searching, insert space into search text
                search_buf.insert_text(" ")

        @kb.add("enter")
        def _on_enter(event):
            filtered = get_filtered_sessions()
            if filtered and 0 <= selected_index < len(filtered):
                result_action["action"] = "resume"
                result_action["session"] = filtered[selected_index]
                event.app.exit(result=result_action)

        @kb.add("c-r")
        def _on_ctrl_r(event):
            filtered = get_filtered_sessions()
            if filtered and 0 <= selected_index < len(filtered):
                result_action["action"] = "rename"
                result_action["session"] = filtered[selected_index]
                event.app.exit(result=result_action)

        @kb.add("c-d")
        def _on_ctrl_d(event):
            filtered = get_filtered_sessions()
            if filtered and 0 <= selected_index < len(filtered):
                result_action["action"] = "delete"
                result_action["session"] = filtered[selected_index]
                event.app.exit(result=result_action)

        def render_header() -> List[tuple]:
            mode_badge = f" [Filter: {filter_mode.upper()}] "
            return [
                ("class:title", " 📂  Resume or Manage Session (Claude Code style) "),
                ("class:mode", mode_badge),
                ("", "\n"),
                ("class:help", " Search: Type to filter · "),
                ("class:key", "↑/↓"),
                ("class:help", " Navigate · "),
                ("class:key", "Enter"),
                ("class:help", " Resume · "),
                ("class:key", "Space"),
                ("class:help", f" {'Hide' if show_preview else 'Show'} Preview · "),
                ("class:key", "Ctrl+R"),
                ("class:help", " Rename · "),
                ("class:key", "Ctrl+D"),
                ("class:help", " Delete\n"),
                ("class:key", " Ctrl+A"),
                ("class:help", " All · "),
                ("class:key", "Ctrl+B"),
                ("class:help", f" Current Branch ({curr_branch or 'none'}) · "),
                ("class:key", "Ctrl+P"),
                ("class:help", f" Current Project · "),
                ("class:key", "Esc"),
                ("class:help", " Cancel\n"),
                ("class:separator", "─" * 80 + "\n"),
            ]

        def render_session_list() -> List[tuple]:
            nonlocal selected_index
            filtered = get_filtered_sessions()
            if not filtered:
                return [("class:empty", "  (No sessions match the current query or filter)\n")]

            if selected_index >= len(filtered):
                selected_index = max(0, len(filtered) - 1)

            # Calculate visible sliding window (max 10 items)
            window_size = 8 if show_preview else 12
            start = max(0, selected_index - window_size // 2)
            end = min(len(filtered), start + window_size)
            if end - start < window_size:
                start = max(0, end - window_size)

            tokens: List[tuple] = []
            for idx in range(start, end):
                s = filtered[idx]
                is_sel = (idx == selected_index)

                agent = (s.get("agent") or "cyc").upper()
                sid = s.get("id") or s.get("session_id") or ""
                raw_title = s.get("title") or s.get("preview") or sid
                title_aligned = fit_width(raw_title, 36)
                msgs = s.get("message_count", 0)
                branch = s.get("git_branch") or ""
                branch_tag = f" ⎇ {branch}" if branch else ""
                branch_aligned = fit_width(branch_tag, 12)

                mtime_raw = s.get("updated_at")
                if mtime_raw:
                    import datetime
                    mtime_str = datetime.datetime.fromtimestamp(mtime_raw).strftime("%Y-%m-%d %H:%M")
                else:
                    mtime_str = "    -           "

                prefix = " ► " if is_sel else "   "
                item_class = "class:selected" if is_sel else "class:item"
                agent_class = f"class:agent-{agent.lower()}" if not is_sel else "class:selected"

                tokens.append((item_class, prefix))
                tokens.append((agent_class, f"[{agent:<8}] "))
                tokens.append((item_class, f"{title_aligned} "))
                tokens.append(("class:meta", f"({msgs:>3} msgs) {mtime_str} {branch_aligned} - {sid[:18]}\n"))

            scroll_info = f" Showing {start+1}-{end} of {len(filtered)} sessions "
            tokens.append(("class:footer", f"\n{scroll_info:^80}\n"))
            return tokens

        def render_preview() -> List[tuple]:
            if not show_preview:
                return []
            filtered = get_filtered_sessions()
            if not filtered or not (0 <= selected_index < len(filtered)):
                return [("class:preview-title", " Preview (no session selected)\n")]

            s = filtered[selected_index]
            sid = s.get("id") or s.get("session_id") or ""
            title = s.get("title") or "(no title)"
            agent = (s.get("agent") or "cyc").upper()
            ws = s.get("workspace") or "(unknown)"
            branch = s.get("git_branch") or "(none)"
            preview = s.get("preview") or "(empty content)"

            return [
                ("class:separator", "─" * 80 + "\n"),
                ("class:preview-title", f" 🔍  Preview: {title}\n"),
                ("class:preview-meta", f"  Session ID: {sid} | Agent: {agent} | Branch: {branch}\n"),
                ("class:preview-meta", f"  Workspace:  {ws}\n"),
                ("class:preview-body", f"  Latest snippet: {preview[:120]}\n"),
            ]

        # Assemble layout
        header_window = Window(FormattedTextControl(render_header), height=4)
        search_prompt_window = Window(
            BufferControl(buffer=search_buf),
            height=1,
            style="class:search-box",
        )
        list_window = Window(FormattedTextControl(render_session_list))
        preview_window = Window(FormattedTextControl(render_preview))

        root_container = HSplit([
            header_window,
            search_prompt_window,
            list_window,
            preview_window,
        ])

        custom_style = Style.from_dict({
            "title": "bold bg:#0284c7 #ffffff",
            "mode": "bold bg:#334155 #f8fafc",
            "help": "#94a3b8",
            "key": "bold #38bdf8",
            "separator": "#334155",
            "search-box": "bg:#1e293b #f8fafc underline",
            "selected": "bold bg:#0284c7 #ffffff",
            "item": "#f8fafc",
            "agent-cyc": "bold #10b981",
            "agent-agy": "bold #a855f7",
            "agent-claude": "bold #f97316",
            "agent-pi": "bold #eab308",
            "agent-opencode": "bold #3b82f6",
            "meta": "#64748b",
            "footer": "dim #64748b",
            "empty": "italic #eab308",
            "preview-title": "bold #38bdf8",
            "preview-meta": "#94a3b8",
            "preview-body": "#e2e8f0",
        })

        app = Application(
            layout=Layout(root_container),
            key_bindings=kb,
            style=custom_style,
            full_screen=False,
            mouse_support=False,
        )

        try:
            picker_result = await app.run_async()
        except Exception as e:
            self.console.print(f"[bold red]Interactive session picker error:[/bold red] {e}")
            return None

        if not picker_result or not picker_result.get("action"):
            return None

        action = picker_result.get("action")
        target_s = picker_result.get("session") or {}
        sid = target_s.get("id") or target_s.get("session_id") or ""
        title = target_s.get("title") or "(no title)"

        if action == "rename":
            try:
                new_title = await input_dialog(
                    title="Rename Session",
                    text=f"Current title: {title}\nEnter new title:",
                    default=target_s.get("title", ""),
                ).run_async()
            except Exception:
                return None
            if new_title and new_title.strip():
                return {"action": "rename", "session": target_s, "new_title": new_title.strip()}
            return None

        elif action == "delete":
            try:
                confirmed = await yes_no_dialog(
                    title="Confirm Delete",
                    text=f"Are you sure you want to delete session '{title}' ({sid})?\nThis action cannot be undone.",
                ).run_async()
            except Exception:
                return None
            if confirmed:
                return {"action": "delete", "session": target_s}
            return None

        return {"action": "resume", "session": target_s}

    def print_tools_table(self, tools: List[Any]):
        table = Table(title=f"Registered Agent Tools ({len(tools)})", box=ROUNDED)
        table.add_column("Tool Name", style="bold cyan")
        table.add_column("Source", justify="center")
        table.add_column("Type", justify="center")
        table.add_column("Description", style="dim")

        for t in tools:
            is_mcp = hasattr(t, "server_name")
            source_badge = f"[bold magenta]MCP:{t.server_name}[/bold magenta]" if is_mcp else "[dim]BUILT-IN[/dim]"
            type_label = "[bold red]MUTATION[/bold red]" if getattr(t, "is_mutation", False) else "[green]READ-ONLY[/green]"
            table.add_row(t.name, source_badge, type_label, t.description)
        self.console.print(table)

    def print_skills_table(self, skills: List[Dict[str, Any]]):
        table = Table(title=f"Available Skills ({len(skills)})", box=ROUNDED)
        table.add_column("Skill Name", style="bold cyan", width=22)
        table.add_column("Source", justify="center", width=14)
        table.add_column("Description", style="dim")

        for s in skills:
            src = s.get("source", "builtin")
            if src == "builtin":
                source_badge = "[dim]BUILT-IN[/dim]"
            elif "workspace" in src:
                source_badge = "[bold green]WORKSPACE[/bold green]"
            elif src in ("antigravity", "gemini"):
                source_badge = "[bold cyan]AGY[/bold cyan]"
            elif src == "claude":
                source_badge = "[bold magenta]CLAUDE[/bold magenta]"
            elif src == "opencode":
                source_badge = "[bold blue]OPENCODE[/bold blue]"
            else:
                source_badge = f"[yellow]{src.upper()}[/yellow]"

            desc = s.get("description", "")
            helpers = s.get("helpers", [])
            if helpers:
                desc += f" [dim cyan]({', '.join(helpers)})[/dim cyan]"

            table.add_row(s["name"], source_badge, desc)
        self.console.print(table)

    def print_models_table(self, models: List[str], current_model: str, provider: str):
        table = Table(title=f"Models available for '{provider}' ({len(models)})", box=ROUNDED)
        table.add_column("Status", style="green", width=8, justify="center")
        table.add_column("Model ID", style="bold cyan")

        for m in models:
            is_active = "[bold green]ACTIVE[/bold green]" if m == current_model else ""
            table.add_row(is_active, m)
        self.console.print(table)

    def print_tokens_stats(self, tokens: int, limit: int, msg_count: int):
        percentage = (tokens / limit) * 100 if limit > 0 else 0
        color = "green" if percentage < 60 else "yellow" if percentage < 85 else "red"
        table = Table(title="Session Context Stats", box=ROUNDED)
        table.add_column("Metric", style="bold")
        table.add_column("Value", style=color)
        table.add_row("Messages in Session", str(msg_count))
        table.add_row("Estimated Tokens", f"{tokens} / {limit}")
        table.add_row("Context Utilization", f"{percentage:.1f}%")
        self.console.print(table)

    def print_usage_stats(
        self,
        provider_name: str,
        model_name: str,
        context_tokens: int,
        context_limit: int,
        msg_count: int,
        prompt_tokens: int,
        completion_tokens: int,
        provider_info: Optional[Dict[str, Any]] = None,
    ):
        table = Table(title="Token & Model Usage / Rate Limits", box=ROUNDED)
        table.add_column("Category", style="bold cyan", width=22)
        table.add_column("Metric / Property", style="bold")
        table.add_column("Value / Status", style="green")

        # 1. Context window utilization
        percentage = (context_tokens / context_limit) * 100 if context_limit > 0 else 0
        ctx_color = "green" if percentage < 60 else "yellow" if percentage < 85 else "red"
        table.add_row("Context Window", "Active Context Tokens", f"[{ctx_color}]{context_tokens} / {context_limit} ({percentage:.1f}%)[/{ctx_color}]")
        table.add_row("Context Window", "Messages in Context", str(msg_count))

        # 2. Cumulative session consumption
        total_session_tokens = prompt_tokens + completion_tokens
        table.add_row("Session Consumption", "Cumulative Prompt Tokens", f"{prompt_tokens:,}")
        table.add_row("Session Consumption", "Cumulative Completion Tokens", f"{completion_tokens:,}")
        table.add_row("Session Consumption", "Total Session Tokens", f"[bold yellow]{total_session_tokens:,}[/bold yellow]")

        # 3. Model & Provider Tier / Limits
        table.add_row("Provider & Model", "Active Provider", provider_name)
        table.add_row("Provider & Model", "Active Model", model_name)

        if provider_info:
            for k, v in provider_info.items():
                if k in ("provider", "model", "quota"):
                    continue
                label = k.replace("_", " ").title()
                table.add_row("Provider Limits", label, str(v))

            if "quota" in provider_info:
                q = provider_info["quota"]
                if "5h" in q:
                    q5 = q["5h"]
                    u = q5["used_pct"]
                    c = "red" if u >= 80 else ("yellow" if u >= 50 else "green")
                    filled = int(u / 10)
                    empty = 10 - filled
                    bar = f"[{c}]{'█' * filled}{'░' * empty}[/{c}]"
                    table.add_row("Rate Limits (Quota)", f"5h Window ({q5['name']})", f"{bar} [{c}]{u}% used[/{c}] (↻ resets in {q5['reset_str']})")
                if "7d" in q:
                    q7 = q["7d"]
                    u = q7["used_pct"]
                    c = "red" if u >= 80 else ("yellow" if u >= 50 else "green")
                    filled = int(u / 10)
                    empty = 10 - filled
                    bar = f"[{c}]{'█' * filled}{'░' * empty}[/{c}]"
                    table.add_row("Rate Limits (Quota)", f"7d Window ({q7['name']})", f"{bar} [{c}]{u}% used[/{c}] (↻ resets in {q7['reset_str']})")
        else:
            table.add_row("Provider Limits", "Account Status", "[dim]Local / Standalone API (No external quota API)[/dim]")

        self.console.print(table)

    def render_formatted_response(self, text: str) -> None:
        """Render response text with separate styled panel for <think>...</think> blocks."""
        import re
        think_pattern = re.compile(r"<think>(.*?)</think>", re.DOTALL)
        match = think_pattern.search(text)
        if match:
            thinking_content = match.group(1).strip()
            rest_content = think_pattern.sub("", text).strip()
            if thinking_content:
                self.console.print(Panel(
                    f"[dim]{thinking_content}[/dim]",
                    title="[bold magenta]Thinking Process[/bold magenta]",
                    border_style="magenta",
                    expand=False,
                ))
            if rest_content:
                self.console.print(Markdown(rest_content))
        else:
            self.console.print(Markdown(text))
        self.console.print()

    async def stream_response(
        self,
        stream_gen: AsyncGenerator[str, None],
        provider: str,
        model: str,
    ) -> str:
        """Stream model response to terminal with optional Live Markdown rendering.
        Detects <think>...</think> thinking blocks and separates them into styled panels.
        Handles KeyboardInterrupt (Ctrl+C) gracefully.
        """
        self.console.print(f"[bold cyan]{provider} ({model})[/bold cyan] > ", end="")
        full_text = ""

        # If not a TTY (piped to file or command), use plain streaming
        if not sys.stdout.isatty() or not self.stream_markdown:
            try:
                async for chunk in stream_gen:
                    sys.stdout.write(chunk)
                    sys.stdout.flush()
                    full_text += chunk
                sys.stdout.write("\n\n")
                sys.stdout.flush()
            except (asyncio.CancelledError, KeyboardInterrupt):
                self.console.print("\n[dim yellow](Interrupted by user)[/dim yellow]\n")
            return full_text

        # Wait for the first chunk with an animated spinner
        first_chunk = None
        try:
            with self.console.status("[dim cyan]Thinking...[/dim cyan]", spinner="dots"):
                try:
                    first_chunk = await stream_gen.__anext__()
                except StopAsyncIteration:
                    first_chunk = None
        except (asyncio.CancelledError, KeyboardInterrupt):
            self.console.print("\n[dim yellow](Interrupted by user)[/dim yellow]\n")
            return full_text

        self.console.print()  # newline before markdown block

        if not first_chunk:
            return full_text

        full_text += first_chunk

        # Live Markdown stream for remaining chunks
        has_think = "<think>" in full_text
        try:
            with Live(Markdown(full_text), console=self.console, refresh_per_second=12, transient=False) as live:
                # Update initial display if first chunk contained thinking
                if "<think>" in full_text and "</think>" not in full_text:
                    has_think = True
                    think_part = full_text.split("<think>", 1)[1]
                    live.update(Markdown(f"> *Thinking...*\n\n```thinking\n{think_part}\n```"))

                async for chunk in stream_gen:
                    full_text += chunk
                    # During streaming, if <think> tags are present, show a thinking indicator or styled text
                    if "<think>" in full_text and "</think>" not in full_text:
                        has_think = True
                        think_part = full_text.split("<think>", 1)[1]
                        live.update(Markdown(f"> *Thinking...*\n\n```thinking\n{think_part}\n```"))
                    elif "<think>" in full_text and "</think>" in full_text:
                        has_think = True
                        parts = full_text.split("</think>", 1)
                        content_part = parts[1].strip()
                        live.update(Markdown(content_part or "> *Thinking complete. Formulating response...*"))
                    else:
                        live.update(Markdown(full_text))

            # After live stream completes:
            # If think tags were present, clear transient display and render the styled Thinking Process panel + clean markdown.
            if has_think:
                self.render_formatted_response(full_text)
            self.console.print()
        except (asyncio.CancelledError, KeyboardInterrupt):
            self.console.print("\n[dim yellow](Interrupted by user)[/dim yellow]\n")

        return full_text

def create_prompt_session(
    history_file: Optional[Path] = None,
    get_models: Optional[Callable[[], List[str]]] = None,
    get_providers: Optional[Callable[[], List[str]]] = None,
    get_sessions: Optional[Callable[[], List[str]]] = None,
    multiline: bool = False,
    bottom_toolbar: Optional[Callable[[], AnyFormattedText]] = None,
) -> PromptSession:
    """Create a configured prompt_toolkit PromptSession with history and keybindings."""
    if history_file:
        history_file.parent.mkdir(parents=True, exist_ok=True)
        history = FileHistory(str(history_file))
    else:
        from prompt_toolkit.history import InMemoryHistory
        history = InMemoryHistory()

    completer = None
    if get_models and get_providers:
        completer = CommandCompleter(
            get_models=get_models,
            get_providers=get_providers,
            get_sessions=get_sessions,
        )

    kb = KeyBindings()

    # Alt+Enter inserts newline in both single-line and multi-line modes
    @kb.add("escape", "enter")
    def _(event):
        event.current_buffer.insert_text("\n")

    return PromptSession(
        history=history,
        completer=completer,
        auto_suggest=AutoSuggestFromHistory(),
        key_bindings=kb,
        multiline=multiline,
        bottom_toolbar=bottom_toolbar,
    )
