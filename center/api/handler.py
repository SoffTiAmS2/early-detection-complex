"""Compatibility import for the control-plane HTTP handler.

The project currently keeps the complete MVP implementation in
`center/server.py`. This module is retained so older imports of
`api.handler.ControlPlaneHandler` keep working.
"""

try:
    from server import ControlPlaneHandler
except ModuleNotFoundError:  # Imported as center.api.handler.
    from center.server import ControlPlaneHandler

__all__ = ["ControlPlaneHandler"]
