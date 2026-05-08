#!/usr/bin/env python3
import argparse
from pathlib import Path
from http.server import ThreadingHTTPServer
from server import ControlPlaneHandler

# Пути по умолчанию (относительно main.py)
DEFAULT_CATALOG = Path("catalog") / "honeypots.json"
DEFAULT_POLICY = Path("config") / "site.example.json"
DEFAULT_STORE = Path("var") / "center" / "events.sqlite3"

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run EDC control-plane MVP")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE)
    return parser.parse_args()

def main() -> None:
    args = parse_args()
    
    # Передаем пути в класс-обработчик
    ControlPlaneHandler.catalog_path = args.catalog
    ControlPlaneHandler.policy_path = args.policy
    ControlPlaneHandler.store_path = args.store
    
    server = ThreadingHTTPServer((args.host, args.port), ControlPlaneHandler)
    print(f"center: listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()

if __name__ == "__main__":
    main()
