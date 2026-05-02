#!/usr/bin/env sh
set -eu

# Останавливает контейнеры выбранного сенсора без удаления логов.
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
SENSOR_NAME=${1:-sensor1}
SENSOR_DIR="$PROJECT_ROOT/sensors/$SENSOR_NAME"

if [ ! -f "$SENSOR_DIR/docker-compose.yml" ]; then
  echo "Config for $SENSOR_NAME not found." >&2
  exit 1
fi

cd "$SENSOR_DIR"
sudo docker compose down
