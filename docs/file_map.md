# Карта Файлов

## Корень

- `README.md` - короткая инструкция по запуску центра и установке сенсора.
- `compose.yml` - контейнерный запуск центра.
- `.gitignore`, `.dockerignore` - исключают runtime, секреты, кэши и старые локальные outputs.

## Центр

- `center/main.py` - основная точка входа центра: парсит CLI-аргументы и запускает приложение.
- `center/app.py` - собирает настроенный HTTP-сервер.
- `center/handler.py` - HTTP routes: веб-страницы, REST API, sensor enroll/status/events, install jobs.
- `center/views.py` - рендеринг HTML-шаблонов.
- `center/templates/` - русскоязычный минималистичный UI центра.
- `center/policy.py` - чтение, запись и валидация политики сенсоров.
- `center/events.py` - SQLite-хранилище событий и выборки для API.
- `center/overview.py` - агрегированное состояние сенсоров, модулей и последних событий.
- `center/installer.py` - установка/обновление сенсора по SSH с журналом прогресса.
- `center/paths.py` - общие пути проекта и значения по умолчанию.
- `center/utils.py` - маленькие общие функции.
- `center/server.py` - совместимый wrapper для старой команды запуска; новая команда использует `center/main.py`.
- `center/Dockerfile` - образ центра с Python, `openssh-client` и `sshpass`.
- `center/README.md` - краткое описание API.

## Сенсор

- `sensor/agent.py` - агент сенсора: регистрируется в центре, забирает desired-state, докладывает status.
- `sensor/runtime.py` - Docker runtime: materialize compose, удаление старых контейнеров, запуск реальных honeypot images, отправка raw logs.
- `sensor/README.md` - детали работы агента.

## Конфигурация

- `catalog/honeypots.json` - каталог Cowrie, OpenCanary, Heralding, Conpot, Dionaea: сервисы, порты, настройки.
- `catalog/README.md` - пояснение каталога.
- `config/site.example.json` - текущая политика стенда: сенсоры, модули, порты, persona.

## Инструменты

- `scripts/run_mvp.sh` - быстрый локальный dry-run.
- `scripts/run_sensor_runtime.sh` - запуск агента сенсора в runtime-режиме.
- `tools/validate_policy.py` - проверка каталога и политики.
- `tools/e2e_reconfigure_test.py` - проверка PATCH API и генерации Docker Compose без запуска тяжёлых образов.

## Runtime

- `var/` - локальное состояние, SQLite-события, applied state. Не хранится в git.
- `central-node/`, `sensors/`, `logs/`, `__pycache__/` - старые или runtime outputs, игнорируются.
