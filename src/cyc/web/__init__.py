"""Cyc Web Server & Remote Control Module."""

from cyc.web.app import create_app
from cyc.web.server import run_web_server

__all__ = ["create_app", "run_web_server"]
