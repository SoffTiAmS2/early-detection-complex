from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CATALOG = ROOT / "catalog" / "honeypots.json"
DEFAULT_DEVICE_PROFILES = ROOT / "catalog" / "device_mask_profiles.json"
EXAMPLE_POLICY = ROOT / "config" / "site.example.json"
DEFAULT_POLICY = ROOT / "config" / "site.local.json"
DEFAULT_STORE = ROOT / "var" / "center" / "events.sqlite3"
MAX_EVENT_LIMIT = 1000
STALE_AFTER_SECONDS = 45
