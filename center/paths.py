from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = ROOT / "catalog" / "honeypots.json"
DEFAULT_POLICY = ROOT / "config" / "site.example.json"
DEFAULT_STORE = ROOT / "var" / "center" / "events.sqlite3"
MAX_EVENT_LIMIT = 1000
STALE_AFTER_SECONDS = 45
