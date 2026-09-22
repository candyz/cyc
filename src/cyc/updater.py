"""Auto-updater for cyc CLI agent."""

import asyncio
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import httpx
from rich.console import Console

from cyc import __version__

console = Console()

GITHUB_RAW_PYPROJECT_URL = "https://raw.githubusercontent.com/candyz/cyc/main/pyproject.toml"
GITHUB_REPO_URL = "git+https://github.com/candyz/cyc.git"


def parse_semver(version_str: str) -> Tuple[int, int, int]:
    """Parse a semantic version string (e.g. '1.4.0' or 'v1.4.1') into (major, minor, patch)."""
    cleaned = version_str.strip().lstrip("v")
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)", cleaned)
    if not m:
        return (0, 0, 0)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def is_newer_version(current_ver: str, remote_ver: str) -> bool:
    """Return True if remote_ver is strictly greater than current_ver."""
    return parse_semver(remote_ver) > parse_semver(current_ver)


@dataclass
class UpdateCheckResult:
    current_version: str
    latest_version: Optional[str]
    has_update: bool
    error: Optional[str] = None


async def fetch_latest_version(timeout: float = 4.0) -> UpdateCheckResult:
    """Fetch the latest version string from GitHub remote repository."""
    current_ver = __version__
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(GITHUB_RAW_PYPROJECT_URL)
            if resp.status_code != 200:
                return UpdateCheckResult(
                    current_version=current_ver,
                    latest_version=None,
                    has_update=False,
                    error=f"HTTP {resp.status_code} fetching remote version",
                )
            
            # Extract version from pyproject.toml
            m = re.search(r'version\s*=\s*"([^"]+)"', resp.text)
            if not m:
                return UpdateCheckResult(
                    current_version=current_ver,
                    latest_version=None,
                    has_update=False,
                    error="Could not parse version from remote pyproject.toml",
                )

            latest_ver = m.group(1).strip()
            has_update = is_newer_version(current_ver, latest_ver)
            return UpdateCheckResult(
                current_version=current_ver,
                latest_version=latest_ver,
                has_update=has_update,
            )
    except Exception as e:
        return UpdateCheckResult(
            current_version=current_ver,
            latest_version=None,
            has_update=False,
            error=str(e),
        )


def detect_install_method() -> str:
    """Detect how cyc was installed (uv_tool, git_repo, pipx, pip)."""
    executable = sys.executable

    # 1. Check if executable is inside uv tool venv
    if "uv/tools/cyc" in executable or ".local/share/uv/tools/cyc" in executable:
        # Check if installed from a local directory repo
        receipt_path = Path.home() / ".local" / "share" / "uv" / "tools" / "cyc" / "uv-receipt.toml"
        if receipt_path.is_file():
            try:
                txt = receipt_path.read_text(encoding="utf-8")
                if "directory =" in txt:
                    return "uv_tool_local"
            except Exception:
                pass
        return "uv_tool"

    # 2. Check if running directly inside a git repo of cyc (e.g. uv run cyc)
    try:
        root_dir = Path(__file__).resolve().parent.parent.parent
        if (root_dir / ".git").is_dir() and (root_dir / "pyproject.toml").is_file():
            return "git_repo"
    except Exception:
        pass

    # 3. Check if running under pipx
    if "pipx/venvs/cyc" in executable:
        return "pipx"

    # 4. Check if uv is available
    if shutil.which("uv"):
        return "uv_tool"

    return "pip"


async def perform_update(force: bool = False) -> bool:
    """Check for update and execute the upgrade command with user feedback."""
    console.print("[dim cyan]Checking for updates...[/dim cyan]")
    check = await fetch_latest_version()

    if check.error:
        console.print(f"[bold red]Failed to check for updates:[/bold red] {check.error}")
        return False

    current = check.current_version
    latest = check.latest_version or current

    if not check.has_update and not force:
        console.print(f"[bold green]cyc is already up to date[/bold green] (version [bold cyan]{current}[/bold cyan]).")
        return True

    if check.has_update:
        console.print(f"✨ [bold green]New version available:[/bold green] [bold cyan]{current}[/bold cyan] → [bold magenta]{latest}[/bold magenta]")
    else:
        console.print(f"[dim]Reinstalling/updating current version [bold cyan]{current}[/bold cyan] (force mode)...[/dim]")

    method = detect_install_method()
    console.print(f"[dim]Detected environment installation: [bold]{method}[/bold][/dim]")

    try:
        with console.status(f"[dim cyan]Updating cyc to v{latest}...[/dim cyan]", spinner="dots"):
            if method == "git_repo":
                root_dir = Path(__file__).resolve().parent.parent.parent
                # 1. git pull
                proc_pull = await asyncio.create_subprocess_exec(
                    "git", "pull", "origin", "main",
                    cwd=str(root_dir),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout_p, stderr_p = await proc_pull.communicate()
                if proc_pull.returncode != 0:
                    console.print(f"[bold red]git pull failed:[/bold red] {stderr_p.decode('utf-8', errors='replace')}")
                    return False

                # 2. reinstall via uv tool if available, or uv sync
                if shutil.which("uv"):
                    cmd = ["uv", "tool", "install", "--force", "--reinstall", str(root_dir)]
                else:
                    cmd = [sys.executable, "-m", "pip", "install", "-e", str(root_dir)]

                proc_install = await asyncio.create_subprocess_exec(
                    *cmd,
                    cwd=str(root_dir),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout_i, stderr_i = await proc_install.communicate()
                if proc_install.returncode != 0:
                    console.print(f"[bold red]Reinstallation failed:[/bold red] {stderr_i.decode('utf-8', errors='replace')}")
                    return False

            elif method == "uv_tool_local":
                # User installed via `uv tool install .` from a local directory
                receipt_path = Path.home() / ".local" / "share" / "uv" / "tools" / "cyc" / "uv-receipt.toml"
                local_dir = None
                try:
                    txt = receipt_path.read_text(encoding="utf-8")
                    m = re.search(r'directory\s*=\s*"([^"]+)"', txt)
                    if m:
                        local_dir = m.group(1)
                except Exception:
                    pass

                if local_dir and Path(local_dir).is_dir():
                    # Pull latest git commit if it's a git repo
                    if (Path(local_dir) / ".git").is_dir():
                        proc_p = await asyncio.create_subprocess_exec(
                            "git", "pull", "origin", "main",
                            cwd=local_dir,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE,
                        )
                        await proc_p.communicate()
                    cmd = ["uv", "tool", "install", "--force", "--reinstall", local_dir]
                else:
                    cmd = ["uv", "tool", "install", "--force", "--reinstall", GITHUB_REPO_URL]

                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()
                if proc.returncode != 0:
                    console.print(f"[bold red]uv tool update failed:[/bold red] {stderr.decode('utf-8', errors='replace')}")
                    return False

            elif method == "uv_tool":
                # Upgrade directly from remote github
                cmd = ["uv", "tool", "install", "--force", "--reinstall", GITHUB_REPO_URL]
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()
                if proc.returncode != 0:
                    console.print(f"[bold red]uv tool update failed:[/bold red] {stderr.decode('utf-8', errors='replace')}")
                    return False

            elif method == "pipx":
                cmd = ["pipx", "install", "--force", GITHUB_REPO_URL]
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()
                if proc.returncode != 0:
                    console.print(f"[bold red]pipx update failed:[/bold red] {stderr.decode('utf-8', errors='replace')}")
                    return False

            else:
                # pip fallback
                cmd = [sys.executable, "-m", "pip", "install", "--upgrade", GITHUB_REPO_URL]
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()
                if proc.returncode != 0:
                    console.print(f"[bold red]pip update failed:[/bold red] {stderr.decode('utf-8', errors='replace')}")
                    return False

        console.print(f"\n[bold green]✓ Successfully updated cyc to version:[/bold green] [bold cyan]{latest}[/bold cyan] 🎉")
        return True
    except Exception as e:
        console.print(f"[bold red]Update error:[/bold red] {e}")
        return False
