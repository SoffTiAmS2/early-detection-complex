#!/usr/bin/env sh
set -eu

# Bootstrap для чистой Armbian/Debian 13 системы.
# Использование:
#   scripts/bootstrap_clean.sh central
#   scripts/bootstrap_clean.sh sensor sensor1

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
MODE=${1:-}
SENSOR_NAME=${2:-sensor1}

if [ "$MODE" = "central" ]; then
  "$PROJECT_ROOT/scripts/install_central.sh"
elif [ "$MODE" = "sensor" ]; then
  "$PROJECT_ROOT/scripts/install_sensor.sh" "$SENSOR_NAME"
  "$PROJECT_ROOT/scripts/start_sensor.sh" "$SENSOR_NAME"
else
  echo "Usage: $0 central | sensor <sensor-name>" >&2
  exit 1
fi

