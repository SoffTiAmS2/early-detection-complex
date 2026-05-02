#!/usr/bin/env sh
set -eu

# Запускает контейнеры выбранного сенсора.
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
SENSOR_NAME=${1:-sensor1}
SENSOR_DIR="$PROJECT_ROOT/sensors/$SENSOR_NAME"

if [ ! -f "$SENSOR_DIR/docker-compose.yml" ]; then
  echo "Config for $SENSOR_NAME not found. Run scripts/generate_sensor.sh first." >&2
  exit 1
fi

cd "$SENSOR_DIR"
sudo docker compose up -d --build
sudo docker compose ps
