#!/usr/bin/env sh
set -eu

# Генерирует локальные ignored-конфигурации сенсоров из config/project.json.
# Запускать из любой директории: путь к проекту определяется по месту скрипта.
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)

cd "$PROJECT_ROOT"
python3 center/orchestrator/generate.py
echo "Generated sensor configs in $PROJECT_ROOT/sensors"
