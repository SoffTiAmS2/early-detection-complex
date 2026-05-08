"""Application assembly for the EDC control plane."""

from __future__ import annotations

from http.server import ThreadingHTTPServer
from pathlib import Path

from .api.handler import ControlPlaneHandler


def create_server(
    host: str,
    port: int,
    catalog_path: Path,
    policy_path: Path,
    store_path: Path,
) -> ThreadingHTTPServer:
    """Create a configured HTTP server instance."""
    ControlPlaneHandler.catalog_path = catalog_path
    ControlPlaneHandler.policy_path = policy_path
    ControlPlaneHandler.store_path = store_path
    return ThreadingHTTPServer((host, port), ControlPlaneHandler)
