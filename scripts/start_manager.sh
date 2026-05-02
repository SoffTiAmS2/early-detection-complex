#!/usr/bin/env sh
set -eu

# Запускает web-конфигуратор профилей, IP-адресов и маскировки.
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
HOST=${MANAGER_HOST:-127.0.0.1}
PORT=${MANAGER_PORT:-8090}

cd "$PROJECT_ROOT"
python3 manager/backend/server.py --host "$HOST" --port "$PORT"

