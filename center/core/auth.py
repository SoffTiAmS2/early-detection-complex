from __future__ import annotations

import base64
import hmac
import os
from dataclasses import dataclass
from http import HTTPStatus
from typing import Mapping


@dataclass(frozen=True)
class AuthConfig:
    username: str
    password: str
    bearer_token: str

    @property
    def enabled(self) -> bool:
        return bool((self.username and self.password) or self.bearer_token)


def load_auth_config() -> AuthConfig:
    return AuthConfig(
        username=os.environ.get("CENTER_AUTH_USER", ""),
        password=os.environ.get("CENTER_AUTH_PASSWORD", ""),
        bearer_token=os.environ.get("CENTER_AUTH_TOKEN", ""),
    )


def is_admin_route(method: str, path: str) -> bool:
    """Routes that can reveal management data or change center state."""
    if path in {"", "/", "/settings", "/db", "/api/overview", "/api/policy", "/api/site", "/api/sensors", "/api/profiles", "/api/db/stats"}:
        return True
    if method == "GET" and path == "/api/events":
        return True
    if method in {"PUT", "PATCH", "DELETE"}:
        return True
    if method == "POST" and (path == "/api/sensors" or path.startswith("/api/sensors/") or path == "/api/db/purge"):
        return True
    return False


def is_authorized(headers: Mapping[str, str], config: AuthConfig | None = None) -> bool:
    config = config or load_auth_config()
    if not config.enabled:
        return True
    auth_header = headers.get("Authorization", "")
    if config.bearer_token and auth_header.startswith("Bearer "):
        supplied = auth_header.removeprefix("Bearer ").strip()
        return hmac.compare_digest(supplied, config.bearer_token)
    if config.username and config.password and auth_header.startswith("Basic "):
        supplied = decode_basic_auth(auth_header)
        expected = f"{config.username}:{config.password}"
        return supplied is not None and hmac.compare_digest(supplied, expected)
    return False


def decode_basic_auth(auth_header: str) -> str | None:
    try:
        encoded = auth_header.removeprefix("Basic ").strip()
        return base64.b64decode(encoded).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None


def auth_required_response() -> tuple[dict[str, str], HTTPStatus]:
    return {"error": "authentication required"}, HTTPStatus.UNAUTHORIZED
