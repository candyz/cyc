"""Workspace Trust Manager - Safeguard against executing agent tools in untrusted directories."""

import json
import time
from pathlib import Path
from typing import Dict, Optional
from rich.console import Console
from rich.panel import Panel

console = Console()
DEFAULT_TRUST_FILE = Path.home() / ".local" / "share" / "clichat" / "trusted_workspaces.json"


class WorkspaceTrustManager:
    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path or DEFAULT_TRUST_FILE
        self._data: Dict[str, Dict] = self._load()

    def _load(self) -> Dict[str, Dict]:
        if not self.storage_path.exists():
            return {}
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save(self) -> None:
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def get_trust_status(self, path: Path) -> Optional[bool]:
        """Check if workspace path or any parent path is trusted.
        Returns:
            True: explicitly trusted
            False: explicitly restricted (untrusted)
            None: not yet configured (first visit)
        """
        resolved = path.resolve()
        # Direct match or parent match
        for p_str, info in self._data.items():
            parent_p = Path(p_str).resolve()
            if resolved == parent_p or parent_p in resolved.parents:
                level = info.get("trust_level")
                if level == "trusted":
                    return True
                elif level == "restricted":
                    return False
        return None

    def set_trust(self, path: Path, trusted: bool) -> None:
        resolved = str(path.resolve())
        self._data[resolved] = {
            "trusted_at": time.time(),
            "trust_level": "trusted" if trusted else "restricted",
        }
        self._save()

    def render_trust_prompt_panel(self, workspace_path: Path):
        resolved = workspace_path.resolve()
        body = (
            f"[bold]Directory:[/bold] [cyan]{resolved}[/cyan]\n\n"
            "This folder contains executable code, project rules, and files.\n"
            "Trusting this workspace enables full autonomous agent capabilities\n"
            "(e.g. running shell commands, writing/editing files).\n\n"
            "  [bold green][y] Trust Workspace[/bold green]   - Enable full agent operations and mutations\n"
            "  [bold yellow][n] Do Not Trust[/bold yellow]     - Run in restricted [yellow]Read-Only[/yellow] mode\n"
            "  [bold red][q] Quit[/bold red]             - Exit clichat immediately"
        )
        console.print(Panel(
            body,
            title="[bold yellow]🛡️  Workspace Trust Confirmation[/bold yellow]",
            border_style="yellow",
            expand=False,
        ))

    async def ensure_workspace_trust(
        self,
        workspace_path: Path,
        auto_trust: Optional[bool] = None,
    ) -> bool:
        """Ensure trust status for workspace. Prompt if not decided."""
        if auto_trust is not None:
            self.set_trust(workspace_path, auto_trust)
            return auto_trust

        status = self.get_trust_status(workspace_path)
        if status is not None:
            return status

        # Prompt user
        self.render_trust_prompt_panel(workspace_path)
        import asyncio
        loop = asyncio.get_running_loop()

        while True:
            try:
                user_choice = await loop.run_in_executor(None, input, "Do you trust the authors of files in this directory? [y/n/q]: ")
                choice = user_choice.strip().lower()
                if choice in ("y", "yes"):
                    self.set_trust(workspace_path, True)
                    console.print(f"[bold green]✓ Workspace trusted:[/bold green] {workspace_path.resolve()}\n")
                    return True
                elif choice in ("n", "no"):
                    self.set_trust(workspace_path, False)
                    console.print(f"[bold yellow]⚠️  Workspace restricted:[/bold yellow] Agent will operate in [bold]Read-Only[/bold] mode.\n")
                    return False
                elif choice in ("q", "quit"):
                    console.print("[dim]Exiting...[/dim]")
                    import sys
                    sys.exit(0)
                else:
                    console.print("[dim]Please enter 'y' to trust, 'n' to restrict, or 'q' to quit.[/dim]")
            except (KeyboardInterrupt, EOFError):
                console.print("\n[dim]Workspace marked as restricted by default.[/dim]")
                self.set_trust(workspace_path, False)
                return False
