#!/usr/bin/env sh
set -eu

# Проверяет состояние выбранного сенсора и доступность центрального узла.
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
SENSOR_NAME=${1:-sensor1}
SENSOR_DIR="$PROJECT_ROOT/sensors/$SENSOR_NAME"
CENTRAL_NODE=$(awk '/central_node:/ {print $2}' "$PROJECT_ROOT/inventory/network.yml")

echo "== systemd/docker =="
systemctl is-active docker || true

echo "== central node =="
ping -c 3 "$CENTRAL_NODE" || true

echo "== i2c =="
ls /dev/i2c-* 2>/dev/null || true

echo "== compose =="
if [ -f "$SENSOR_DIR/docker-compose.yml" ]; then
  cd "$SENSOR_DIR"
  sudo docker compose ps || true
  sudo docker compose logs --tail=50 || true
else
  echo "No generated compose file for $SENSOR_NAME"
fi
