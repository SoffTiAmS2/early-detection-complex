#!/usr/bin/env sh
set -eu

# Запускает интерактивный конфигуратор профилей, IP и маскировки.
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)

cd "$PROJECT_ROOT"
python3 manager/cli.py

