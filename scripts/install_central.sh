#!/usr/bin/env sh
set -eu

# Устанавливает Docker/Compose и запускает центральную консоль.
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)

sudo apt update
sudo apt install -y docker.io curl
sudo apt install -y docker-compose-plugin || sudo apt install -y docker-compose
sudo systemctl enable --now docker

cd "$PROJECT_ROOT/center"
if sudo docker compose version >/dev/null 2>&1; then
  sudo docker compose up -d --build
  sudo docker compose ps
else
  sudo docker-compose up -d --build
  sudo docker-compose ps
fi

echo "Central dashboard: http://127.0.0.1:8080/dashboard"
echo "Manager console:   http://127.0.0.1:8090"
