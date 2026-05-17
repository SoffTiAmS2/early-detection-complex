#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from center.core.paths import DEFAULT_STORE
from center.persistence.honeypot_logs import reparse_honeypot_events


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild normalized honeypot_events from raw_honeypot_logs.")
    parser.add_argument("--store", default=str(DEFAULT_STORE), help="SQLite store path when CENTER_DB_DSN is not set")
    parser.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args()

    result = reparse_honeypot_events(Path(args.store), args.batch_size)
    print(f"raw={result['raw']} normalized={result['normalized']} skipped={result.get('skipped', 0)}")


if __name__ == "__main__":
    main()
