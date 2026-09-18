import asyncio
import sys
from pathlib import Path
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import CompleteEvent, Completer, Completion, PathCompleter
from prompt_toolkit.document import Document
from prompt_toolkit.formatted_text import HTML, AnyFormattedText
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
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
            "/loop",
            "/tools",
            "/skills",
            "/skill",
            "/trust",
            "/sessions",
            "/resume",
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
            "/clear",
            "/exit",
            "/quit",
        ]

    def get_sessions(self, agent: Optional[str] = None) -> List[str]:
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
            # Tab completion for sources: all, cyc, agy, claude, pi, opencode
            sources = ["all", "cyc", "agy", "claude", "pi", "opencode"]
            for s in sources:
                if s.startswith(arg_prefix.lower()):
                    yield Completion(s, start_position=-len(arg_prefix))
        elif cmd == "/resume":
            if self.get_sessions:
                # Check if user has typed an agent prefix, e.g. "/resume agy "
                resume_parts = arg_prefix.split(maxsplit=1)
                agent_names = ["cyc", "agy", "claude", "pi", "opencode"]

                if not resume_parts:
                    # User typed "/resume " with no text yet
                    for an in agent_names:
                        yield Completion(an, start_position=0)
                    for s in self.get_sessions(None):
                        yield Completion(s, start_position=0)
                elif len(resume_parts) == 1 and not arg_prefix.endswith(" "):
                    # Still typing the first argument: could be an agent name or a session ID / LATEST
                    first_tok = resume_parts[0].lower()
                    # First yield matching agent names
                    for an in agent_names:
                        if an.startswith(first_tok):
                            yield Completion(an, start_position=-len(first_tok))
                    # Also yield matching session IDs directly
                    for s in self.get_sessions(None):
                        if s.lower().startswith(first_tok):
                            yield Completion(s, start_position=-len(first_tok))
                else:
                    # User specified first argument and pressed space, or is typing session id for that agent
                    target_agent = resume_parts[0].lower()
                    session_query = resume_parts[1] if len(resume_parts) > 1 else ""

                    if target_agent in agent_names:
                        filter_agent = None if target_agent == "all" else target_agent
                        for s in self.get_sessions(filter_agent):
                            if s.lower().startswith(session_query.lower()):
                                yield Completion(s, start_position=-len(session_query))
                    else:
                        # First argument was not a recognized agent name, fallback to all sessions
                        for s in self.get_sessions(None):
                            if s.lower().startswith(arg_prefix.lower()):
                                yield Completion(s, start_position=-len(arg_prefix))
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
        table.add_column("Agent / Source", style="bold yellow", justify="center")
        table.add_column("Session ID", style="bold cyan")
        table.add_column("Mode", justify="center")
        table.add_column("Provider / Model", style="green")
        table.add_column("Msgs", justify="right")
        table.add_column("Last Updated", style="dim")
        table.add_column("Latest Preview", style="dim", max_width=40, overflow="ellipsis")

        import datetime
        for s in sessions:
            m_time = datetime.datetime.fromtimestamp(s["updated_at"]).strftime("%Y-%m-%d %H:%M")
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

            table.add_row(
                agent_col,
                s["session_id"] if "session_id" in s else s.get("id", "-"),
                mode_badge,
                prov_model,
                str(s.get("message_count", 0)),
                m_time,
                s.get("preview", ""),
            )
        self.console.print(table)

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
                if k in ("provider", "model"):
                    continue
                label = k.replace("_", " ").title()
                table.add_row("Provider Limits", label, str(v))
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
        try:
            with Live(Markdown(full_text), console=self.console, refresh_per_second=12, transient=False) as live:
                # Update initial display if first chunk contained thinking
                if "<think>" in full_text and "</think>" not in full_text:
                    think_part = full_text.split("<think>", 1)[1]
                    live.update(Markdown(f"> *Thinking...*\n\n```thinking\n{think_part}\n```"))

                async for chunk in stream_gen:
                    full_text += chunk
                    # During streaming, if <think> tags are present, show a thinking indicator or styled text
                    if "<think>" in full_text and "</think>" not in full_text:
                        think_part = full_text.split("<think>", 1)[1]
                        live.update(Markdown(f"> *Thinking...*\n\n```thinking\n{think_part}\n```"))
                    elif "<think>" in full_text and "</think>" in full_text:
                        parts = full_text.split("</think>", 1)
                        content_part = parts[1].strip()
                        live.update(Markdown(content_part or "> *Thinking complete. Formulating response...*"))
                    else:
                        live.update(Markdown(full_text))

            # After live streaming completes, if <think> tags were present, re-render cleanly
            if "<think>" in full_text:
                self.console.clear()
                self.console.print(f"[bold cyan]{provider} ({model})[/bold cyan] > ")
                self.render_formatted_response(full_text)
            else:
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
