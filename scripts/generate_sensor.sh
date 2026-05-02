#!/usr/bin/env sh
set -eu

# Генерирует конфигурации sensor1..sensor3 из inventory/.
# Запускать из любой директории: путь к проекту определяется по месту скрипта.
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)

cd "$PROJECT_ROOT"
python3 orchestrator/generate.py
echo "Generated sensor configs in $PROJECT_ROOT/sensors"
