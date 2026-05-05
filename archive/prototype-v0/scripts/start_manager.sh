#!/usr/bin/env sh
set -eu

# Запускает API-manager локально, без Docker. Для обычного запуска центра
# используй scripts/install_central.sh: он поднимает manager в контейнере.
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
HOST=${MANAGER_HOST:-127.0.0.1}
PORT=${MANAGER_PORT:-8090}

cd "$PROJECT_ROOT"
python3 center/manager/backend/server.py --host "$HOST" --port "$PORT"
