#!/usr/bin/env sh
set -eu

# Устанавливает базовые зависимости и запускает центральный узел.
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)

sudo apt update
sudo apt install -y docker.io docker-cli docker-compose python3 curl
sudo systemctl enable --now docker

cd "$PROJECT_ROOT/central-node"
sudo docker compose up -d --build
sudo docker compose ps
