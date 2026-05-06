#!/usr/bin/env bash
set -euo pipefail

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"

python3 sensor/agent.py \
  --center "${EDC_CENTER_URL:-http://192.168.0.196:8080}" \
  --sensor-id "${EDC_SENSOR_ID:-sensor1}" \
  --interval "${EDC_INTERVAL:-15}" \
  --serve
