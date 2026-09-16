import asyncio
import sys
from pathlib import Path
from typing import AsyncGenerator, Callable, Dict, List, Optional

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import CompleteEvent, Completer, Completion, PathCompleter
from prompt_toolkit.document import Document
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from rich.box import ROUNDED
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.theme import Theme

from clichat import __version__

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
    ):
        self.get_models = get_models
        self.get_providers = get_providers
        self.path_completer = PathCompleter(expanduser=True)
        self.commands = [
            "/help",
            "/models",
            "/model",
            "/provider",
            "/system",
            "/tokens",
            "/multiline",
            "/save",
            "/load",
            "/clear",
            "/exit",
            "/quit",
        ]

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

        if cmd == "/model":
            for m in self.get_models():
                if m.lower().startswith(arg_prefix.lower()):
                    yield Completion(m, start_position=-len(arg_prefix))
        elif cmd == "/provider":
            for p in self.get_providers():
                if p.lower().startswith(arg_prefix.lower()):
                    yield Completion(p, start_position=-len(arg_prefix))
        elif cmd in ("/save", "/load"):
            # Delegate to PathCompleter with modified document
            sub_doc = Document(arg_prefix, cursor_position=len(arg_prefix))
            for c in self.path_completer.get_completions(sub_doc, complete_event):
                yield c

class TerminalUI:
    def __init__(self, stream_markdown: bool = True):
        self.stream_markdown = stream_markdown
        self.console = console

    def print_banner(self, provider: str, model: str, multiline: bool = False):
        mode_text = "[magenta]Multi-line Mode[/magenta]" if multiline else "[dim]Single-line Mode[/dim]"
        title = f"[bold green]clichat[/bold green] [dim]v{__version__}[/dim]"
        body = (
            f"Provider: [bold cyan]{provider}[/bold cyan]  |  Model: [bold cyan]{model}[/bold cyan]  |  {mode_text}\n"
            f"[dim]Commands: /help, /models, /model <name>, /provider <name>, /multiline, /exit[/dim]"
        )
        self.console.print(Panel(body, title=title, border_style="cyan", box=ROUNDED))

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

    async def stream_response(
        self,
        stream_gen: AsyncGenerator[str, None],
        provider: str,
        model: str,
    ) -> str:
        """Stream model response to terminal with optional Live Markdown rendering.
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

        # Live Markdown stream
        self.console.print()  # newline before markdown block
        try:
            with Live(Markdown(""), console=self.console, refresh_per_second=12, transient=False) as live:
                async for chunk in stream_gen:
                    full_text += chunk
                    live.update(Markdown(full_text))
            self.console.print()
        except (asyncio.CancelledError, KeyboardInterrupt):
            self.console.print("\n[dim yellow](Interrupted by user)[/dim yellow]\n")

        return full_text

def create_prompt_session(
    history_file: Optional[Path] = None,
    get_models: Optional[Callable[[], List[str]]] = None,
    get_providers: Optional[Callable[[], List[str]]] = None,
    multiline: bool = False,
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
        completer = CommandCompleter(get_models=get_models, get_providers=get_providers)

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
    )
