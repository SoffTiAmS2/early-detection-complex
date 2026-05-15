from __future__ import annotations

import html
from pathlib import Path
from typing import Any


TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


def render_admin_page(policy: dict[str, Any]) -> str:
    site = policy.get("site", {}) if isinstance(policy.get("site"), dict) else {}
    title = html.escape(str(site.get("name") or "early-detection-complex"))
    return (TEMPLATES_DIR / "admin.html").read_text(encoding="utf-8").replace("{{SITE_NAME}}", title)


def render_database_page(policy: dict[str, Any]) -> str:
    site = policy.get("site", {}) if isinstance(policy.get("site"), dict) else {}
    title = html.escape(str(site.get("name") or "early-detection-complex"))
    return (TEMPLATES_DIR / "database.html").read_text(encoding="utf-8").replace("{{SITE_NAME}}", title)


def render_mask_page(policy: dict[str, Any]) -> str:
    site = policy.get("site", {}) if isinstance(policy.get("site"), dict) else {}
    title = html.escape(str(site.get("name") or "early-detection-complex"))
    return (TEMPLATES_DIR / "mask.html").read_text(encoding="utf-8").replace("{{SITE_NAME}}", title)


def render_profiles_page(policy: dict[str, Any]) -> str:
    site = policy.get("site", {}) if isinstance(policy.get("site"), dict) else {}
    title = html.escape(str(site.get("name") or "early-detection-complex"))
    return (TEMPLATES_DIR / "profiles.html").read_text(encoding="utf-8").replace("{{SITE_NAME}}", title)
