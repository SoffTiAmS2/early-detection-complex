#!/usr/bin/env bash
set -euo pipefail

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"

python3 center/server.py --host 127.0.0.1 --port 8080 &
center_pid=$!
trap 'kill "$center_pid" 2>/dev/null || true' EXIT

sleep 1
python3 sensor/agent.py --center http://127.0.0.1:8080 --sensor-id sensor1 --once
curl -fsS http://127.0.0.1:8080/api/sensors
printf '\n'
