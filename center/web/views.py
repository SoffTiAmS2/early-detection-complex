from __future__ import annotations

import html
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse


TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


def render_template(name: str, policy: dict[str, Any]) -> str:
    site = policy.get("site", {}) if isinstance(policy.get("site"), dict) else {}
    title = html.escape(str(site.get("name") or "early-detection-complex"))
    grafana_url = html.escape(_grafana_url(site))
    grafana_logs_url = html.escape(grafana_url.rstrip("/") + "/d/edc-honeypot-logs/edc-honeypot-logs")
    return (
        (TEMPLATES_DIR / name)
        .read_text(encoding="utf-8")
        .replace("{{SITE_NAME}}", title)
        .replace("{{GRAFANA_URL}}", grafana_url)
        .replace("{{GRAFANA_LOGS_URL}}", grafana_logs_url)
    )


def _grafana_url(site: dict[str, Any]) -> str:
    observability = site.get("observability") if isinstance(site.get("observability"), dict) else {}
    configured = os.environ.get("GRAFANA_URL") or site.get("grafana_url") or observability.get("grafana_url")
    if configured:
        return str(configured)
    central_url = str(site.get("central_url") or "")
    if central_url:
        parsed = urlparse(central_url)
        host = parsed.hostname or "127.0.0.1"
        netloc = f"{host}:3000"
        return urlunparse((parsed.scheme or "http", netloc, "", "", "", ""))
    return "http://127.0.0.1:3000"


def render_admin_page(policy: dict[str, Any]) -> str:
    return render_template("admin.html", policy)


def render_database_page(policy: dict[str, Any]) -> str:
    return render_template("database.html", policy)


def render_mask_page(policy: dict[str, Any]) -> str:
    return render_template("mask.html", policy)


def render_profiles_page(policy: dict[str, Any]) -> str:
    return render_template("profiles.html", policy)
