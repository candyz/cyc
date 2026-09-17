import difflib
from pathlib import Path
from typing import Optional
from rich.panel import Panel
from rich.syntax import Syntax
from rich.console import Console

console = Console()

def generate_unified_diff(
    filepath: str,
    original_text: str,
    new_text: str,
) -> str:
    """Generate a standard unified diff string between original and new text."""
    orig_lines = original_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)
    diff = difflib.unified_diff(
        orig_lines,
        new_lines,
        fromfile=f"a/{filepath}",
        tofile=f"b/{filepath}",
    )
    return "".join(diff)

def render_diff_panel(
    filepath: str,
    original_text: str,
    new_text: str,
    action_title: str = "File Modification Preview",
) -> None:
    """Render a colored unified diff panel to the terminal using Rich Syntax."""
    diff_str = generate_unified_diff(filepath, original_text, new_text)
    if not diff_str.strip():
        diff_str = "[No visible changes]"
    syntax = Syntax(diff_str, "diff", theme="monokai", line_numbers=False)
    console.print(Panel(syntax, title=f"[bold yellow]{action_title}[/bold yellow]: {filepath}", border_style="yellow"))
