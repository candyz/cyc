import asyncio
import os
import secrets
import sys
import webbrowser
from pathlib import Path
from typing import Optional

import uvicorn
from rich.console import Console
from rich.panel import Panel

from cyc import __version__
from cyc.config import Config, load_config
from cyc.web.app import create_app

console = Console()


async def run_web_server(
    config: Optional[Config] = None,
    host: Optional[str] = None,
    port: Optional[int] = None,
    auth_token: Optional[str] = None,
    open_browser: bool = True,
    workspace_path: Optional[Path] = None,
):
    """Start uvicorn ASGI server hosting cyc Web Interface."""
    cfg = config or load_config()
    server_host = host or cfg.web.host or "127.0.0.1"
    server_port = port or cfg.web.port or 8888
    ws_path = workspace_path or Path.cwd()

    # Generate random 32-char token if none provided in args or config
    token = auth_token if auth_token is not None else (cfg.web.auth_token or secrets.token_urlsafe(24))

    app = create_app(config=cfg, auth_token=token, workspace_path=ws_path)

    use_ssl = bool(cfg.web.ssl_cert and cfg.web.ssl_key)
    scheme = "https" if use_ssl else "http"
    display_host = "localhost" if server_host in ("0.0.0.0", "127.0.0.1") else server_host
    app_url = f"{scheme}://{display_host}:{server_port}/?token={token}"

    panel_text = (
        f"[bold green]cyc Web Interface v{__version__}[/bold green]\n\n"
        f"• Workspace: [cyan]{ws_path.resolve()}[/cyan]\n"
        f"• Server:    [bold]{scheme}://{server_host}:{server_port}[/bold]\n"
        f"• URL:       [bold underline cyan]{app_url}[/bold underline cyan]\n"
        f"• Auth Token: [yellow]{token}[/yellow]\n"
        f"• SSL/TLS:   [{'green' if use_ssl else 'dim'}]{'Enabled' if use_ssl else 'Disabled'}[/{'green' if use_ssl else 'dim'}]\n\n"
        "[dim]Press Ctrl+C to stop the Web server.[/dim]"
    )
    console.print(Panel(panel_text, title="🌐 Cyc Web Service Running", border_style="green", expand=False))

    if open_browser:
        try:
            webbrowser.open(app_url)
        except Exception:
            pass

    uvicorn_kwargs = {
        "host": server_host,
        "port": server_port,
        "log_level": "info",
    }
    if use_ssl:
        uvicorn_kwargs["ssl_certfile"] = cfg.web.ssl_cert
        uvicorn_kwargs["ssl_keyfile"] = cfg.web.ssl_key

    server_config = uvicorn.Config(app, **uvicorn_kwargs)
    server = uvicorn.Server(server_config)
    await server.serve()

