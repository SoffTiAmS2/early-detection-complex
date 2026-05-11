# Карта Файлов

## Корень

- `README.md` - короткая инструкция по запуску центра и установке сенсора.
- `compose.yml` - контейнерный запуск центра.
- `Makefile` - короткие команды `make up`, `make logs`, `make check`, `make e2e`.
- `pyproject.toml`, `requirements.txt` - метаданные Python-проекта; runtime-зависимостей нет.
- `.gitignore`, `.dockerignore` - исключают runtime, секреты, кэши и старые локальные outputs.

## Центр

- `center/main.py` - основная точка входа центра: парсит CLI-аргументы и запускает приложение.
- `center/app.py` - собирает настроенный HTTP-сервер.
- `center/api/handler.py` - HTTP routes: веб-страницы, REST API, sensor enroll/status/events, install jobs.
- `center/core/policy.py` - чтение, запись и валидация политики сенсоров.
- `center/core/overview.py` - агрегированное состояние сенсоров, модулей и последних событий.
- `center/core/paths.py` - общие пути проекта и значения по умолчанию.
- `center/core/utils.py` - маленькие общие функции.
- `center/persistence/events.py` - SQLite-хранилище событий и выборки для API.
- `center/services/installer.py` - установка/обновление сенсора по SSH с журналом прогресса.
- `center/web/views.py` - рендеринг HTML-шаблонов.
- `center/web/templates/` - русскоязычный минималистичный UI центра.
- `center/server.py` - совместимый wrapper для старой команды запуска; новая команда использует `center/main.py`.
- `center/Dockerfile` - образ центра с Python, `openssh-client` и `sshpass`.
- `center/README.md` - краткое описание API.

## Сенсор

- `sensor/agent.py` - агент сенсора: регистрируется в центре, забирает desired-state, докладывает status.
- `sensor/agent_state.py` - payload enrollment/status и локальный applied state.
- `sensor/runtime.py` - Docker runtime: compose, удаление старых контейнеров, запуск images, отправка сырых логов.
- `sensor/runtime_configs.py` - генерация конфигов Cowrie, OpenCanary, Heralding и Conpot.
- `sensor/runtime_helpers.py` - общие helper-функции и константы runtime.
- `sensor/runtime_status.py` - чтение Docker container status/health details.
- `sensor/README.md` - детали работы агента.

## Конфигурация

- `catalog/honeypots.json` - каталог Cowrie, OpenCanary, Heralding, Conpot, Dionaea: сервисы, порты, настройки.
- `catalog/README.md` - пояснение каталога.
- `config/site.example.json` - пример политики стенда: сенсоры, модули, порты, persona.
- `config/site.local.json` - рабочая политика центра, создаётся локально и не хранится в git.

## Инструменты

- `docs/beginner_guide.md` - простое объяснение запуска, установки сенсора, логов и карты кода.
- `docs/network.md` - схема портов, направлений соединений и auth-настроек.
- `scripts/run_mvp.sh` - быстрый локальный dry-run.
- `scripts/run_sensor_runtime.sh` - запуск агента сенсора в runtime-режиме.
- `scripts/check.sh` - быстрые проверки проекта.
- `tools/validate_policy.py` - проверка каталога и политики.
- `tools/e2e_reconfigure_test.py` - проверка PATCH API и генерации Docker Compose без запуска тяжёлых образов.

## Runtime / Локальное Состояние

- `var/` - локальное состояние, SQLite-события, applied state. Не хранится в git.
- `central-node/`, `sensors/`, `logs/`, `__pycache__/` - старые или runtime outputs, игнорируются.
