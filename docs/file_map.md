# Карта Файлов Проекта

Этот документ объясняет, зачем нужен каждый tracked-файл в репозитории. Generated/runtime-файлы вроде `sensors/`, `.env`, `logs/`, `events.jsonl`, `config/network.yml`, `config/sensors.yml` не хранятся в git.

## Корень

- `.dockerignore` - исключает секреты, runtime-логи, generated-сенсоры и кэш из Docker build context.
- `.gitignore` - не дает случайно закоммитить `.env`, логи, generated-файлы сенсоров и локальные дампы документации.
- `README.md` - главный вход: что это за проект, как запустить центр, как поставить сенсор.

## Конфигурация

- `config/project.json` - единственный tracked источник настройки стенда: сеть, центр, сенсоры, Cowrie, порты, маскировка.

## Центр

- `center/__init__.py` - делает `center` Python-пакетом, чтобы backend и generator могли импортировать общий каталог.
- `center/docker-compose.yml` - Docker stack центра: collector на `8080`, manager на `8090`.

## Collector

- `center/collector/Dockerfile` - образ центрального приемника событий.
- `center/collector/server.py` - HTTP API collector: принимает события, хранит JSONL, отдает `/health`, `/api/events`, `/api/sensors`.

## Manager

- `center/manager/Dockerfile` - образ web-manager с Ansible, генератором и исходниками сенсора.
- `center/manager/backend/server.py` - backend web-консоли: читает/сохраняет проект, валидирует конфиг, запускает генерацию и Ansible jobs.
- `center/manager/frontend/index.html` - разметка web-интерфейса.
- `center/manager/frontend/app.js` - логика интерфейса: статусы, сенсоры, Cowrie-настройки, порты, deploy/cancel.
- `center/manager/frontend/styles.css` - минималистичные стили web-интерфейса.

## Каталог Honeypot

- `center/honeypots/__init__.py` - пакет для общего каталога honeypot.
- `center/honeypots/catalog.py` - справочник реально поддержанных приманок. Сейчас там Cowrie, его сервисы SSH/Telnet, host-порты и поля настроек.

## Генератор

- `center/orchestrator/generate.py` - превращает `config/project.json` в ignored-папку `sensors/<name>/`: `.env`, `docker-compose.yml`, `cowrie.cfg`, runtime-директории.

## Ansible

- `center/ansible/deploy_sensor.yml` - playbook установки сенсора по SSH: ставит Docker/Compose, копирует `sensor/Dockerfile`, runtime-скрипты и generated-конфиг, затем запускает `docker compose up -d --build`.

## Sensor

- `sensor/Dockerfile` - единый образ сенсора `edc-sensor` на базе `cowrie/cowrie:latest`.
- `sensor/runtime/entrypoint.py` - стартует внутри одного контейнера Cowrie, log-agent и display-agent.
- `sensor/runtime/log_agent.py` - читает `cowrie.json` и отправляет события в центр, не теряя их при временной недоступности collector.
- `sensor/runtime/display_agent.py` - печатает локальный статус сенсора и связь с центром.

## Scripts

- `scripts/install_central.sh` - установка Docker/Compose и запуск центра.
- `scripts/generate_sensor.sh` - dev-helper для ручной генерации `sensors/<name>/`.
- `scripts/start_manager.sh` - dev-helper для локального запуска manager без Docker.

## Docs

- `docs/architecture.md` - общая архитектура.
- `docs/deception_masking.md` - как работает маскировка и Cowrie-конфигурация.
- `docs/deployment.md` - установка и эксплуатация центра/сенсора.
- `docs/experiments.md` - минимальные эксперименты для проверки стенда.
- `docs/file_map.md` - этот файл.
- `docs/full_report.md` - ссылки на полный отчет ВКР во внешнем Obsidian Vault.
- `docs/functions_io.md` - входы и выходы основных API/скриптов/компонентов.
- `docs/honeypot_catalog.md` - что сейчас поддерживает каталог приманок.
- `docs/masking.md` - краткие тезисы по deception-маскировке.
- `docs/thesis_notes.md` - заметки для ВКР.
- `docs/web_configurator.md` - web-консоль и ее API.
