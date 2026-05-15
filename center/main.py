#!/usr/bin/env python3
"""Command-line entrypoint for the EDC center."""

from __future__ import annotations

import argparse
from pathlib import Path

from .app import create_server
from .core.paths import DEFAULT_CATALOG, DEFAULT_DEVICE_PROFILES, DEFAULT_POLICY, DEFAULT_STORE, EXAMPLE_POLICY
from .core.utils import ensure_file_from_example


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run EDC center")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--profiles", type=Path, default=DEFAULT_DEVICE_PROFILES)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.policy == DEFAULT_POLICY:
        ensure_file_from_example(DEFAULT_POLICY, EXAMPLE_POLICY)
    server = create_server(
        host=args.host,
        port=args.port,
        catalog_path=args.catalog,
        profile_path=args.profiles,
        policy_path=args.policy,
        store_path=args.store,
    )
    print(f"center: listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\ncenter: stopped")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
