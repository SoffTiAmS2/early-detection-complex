from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from center.core.policy import modules_by_id

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


def load_template(name: str) -> str:
    return (TEMPLATES_DIR / name).read_text(encoding="utf-8")


def render_dashboard(policy: dict[str, Any]) -> str:
    site_name = html.escape(str(policy.get("site", {}).get("name", "EDC")))
    return load_template("dashboard.html").replace("{{SITE_NAME}}", site_name)


def render_honeypot_page(policy: dict[str, Any], catalog: dict[str, Any], sensor_id: str, module_id: str) -> str | None:
    catalog_module = modules_by_id(catalog).get(module_id)
    if not catalog_module:
        return None
    replacements = {
        "{{TITLE}}": html.escape(str(catalog_module.get("title") or module_id)),
        "{{MODULE_ID}}": html.escape(module_id),
        "{{SENSOR_ID}}": html.escape(sensor_id),
    }
    page = load_template("honeypot.html")
    for token, value in replacements.items():
        page = page.replace(token, value)
    return page
