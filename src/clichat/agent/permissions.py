import asyncio
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, Optional, Set
from rich.console import Console
from rich.panel import Panel
from clichat.agent.tools.base import Tool
from clichat.agent.diff import render_diff_panel

console = Console()

class PermissionMode(str, Enum):
    INTERACTIVE = "interactive"
    AUTO = "auto"
    READ_ONLY = "read_only"

class PermissionManager:
    def __init__(self, mode: PermissionMode = PermissionMode.INTERACTIVE):
        self.mode = mode
        self.always_allowed_tools: Set[str] = set()

    async def check_permission(self, tool: Tool, args: Dict, prompt_text: Optional[str] = None) -> bool:
        # Read-only tools are always safe to execute
        if not tool.is_mutation:
            return True

        # Read-only mode denies all mutations
        if self.mode == PermissionMode.READ_ONLY:
            console.print(f"[bold red]Blocked:[/bold red] '{tool.name}' rejected (Running in read-only mode).")
            return False

        # Auto mode automatically approves all operations
        if self.mode == PermissionMode.AUTO:
            return True

        # If user previously chose 'always allow' for this tool in this session
        if tool.name in self.always_allowed_tools:
            return True

        # Render visual previews for file changes
        if tool.name == "replace_file_content":
            filepath = args.get("path", "")
            target = args.get("target", "")
            replacement = args.get("replacement", "")
            orig_file = Path(filepath).expanduser()
            if orig_file.exists() and orig_file.is_file():
                orig_text = orig_file.read_text(encoding="utf-8", errors="replace")
                new_text = orig_text.replace(target, replacement, 1)
                render_diff_panel(filepath, orig_text, new_text, "Replace Content Preview")
        elif tool.name == "write_file":
            filepath = args.get("path", "")
            new_content = args.get("content", "")
            orig_file = Path(filepath).expanduser()
            orig_text = orig_file.read_text(encoding="utf-8", errors="replace") if orig_file.exists() else ""
            action = "Overwriting File Preview" if orig_file.exists() else "Create New File Preview"
            render_diff_panel(filepath, orig_text, new_content, action)
        elif tool.name == "run_command":
            cmd = args.get("command", "")
            cwd = args.get("cwd", ".")
            console.print(Panel(f"[bold cyan]Command:[/bold cyan] {cmd}\n[dim]Working directory: {cwd}[/dim]", title="Shell Command Execution", border_style="yellow"))
        elif tool.name == "run_script":
            code = args.get("code", "")
            lang = args.get("language", "python")
            from rich.syntax import Syntax
            syntax = Syntax(code, lang, theme="monokai", line_numbers=True)
            console.print(Panel(syntax, title=f"Programmatic Tool Script (PTC): {lang}", border_style="yellow"))

        # Prompt user for confirmation
        question = prompt_text or f"Allow '{tool.name}' to execute? [y]es / [n]o / [a]lways for this session: "
        try:
            loop = asyncio.get_running_loop()
            user_choice = await loop.run_in_executor(None, input, question)
            choice = user_choice.strip().lower()

            if choice in ("y", "yes", ""):
                return True
            elif choice in ("a", "all", "always"):
                self.always_allowed_tools.add(tool.name)
                console.print(f"[dim green]'{tool.name}' will be automatically approved for the rest of this session.[/dim green]")
                return True
            else:
                console.print(f"[bold red]Action cancelled by user.[/bold red]")
                return False
        except (KeyboardInterrupt, EOFError):
            console.print(f"\n[bold red]Action cancelled.[/bold red]")
            return False
