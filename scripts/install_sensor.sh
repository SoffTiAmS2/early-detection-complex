#!/usr/bin/env sh
set -eu

# Готовит Banana Pi Pro к роли сенсора.
# Скрипт ставит зависимости, генерирует конфигурации и проверяет I2C/сеть.
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
SENSOR_NAME=${1:-sensor1}

sudo apt update
sudo apt install -y docker.io docker-cli docker-compose python3 python3-venv python3-pip i2c-tools curl netcat-openbsd rsync
sudo systemctl enable --now docker

cd "$PROJECT_ROOT"
python3 orchestrator/generate.py

if [ ! -d "$PROJECT_ROOT/sensors/$SENSOR_NAME" ]; then
  echo "Unknown sensor: $SENSOR_NAME" >&2
  exit 1
fi

echo "Checking I2C devices, if the bus is enabled:"
ls /dev/i2c-* 2>/dev/null || echo "No /dev/i2c-* devices found; enable I2C in Armbian settings if LCD is required."

CENTRAL_NODE=$(awk '/central_node:/ {print $2}' "$PROJECT_ROOT/inventory/network.yml")
echo "Checking central node connectivity: $CENTRAL_NODE"
ping -c 3 "$CENTRAL_NODE" || echo "Central node is not reachable yet; check network or start central node."

echo "Sensor $SENSOR_NAME is prepared. Start it with: scripts/start_sensor.sh $SENSOR_NAME"
