# Карта Файлов Проекта

Этот документ объясняет, зачем нужен каждый tracked-файл в репозитории. Generated/runtime-файлы вроде `sensors/`, `.env`, `logs/`, `events.jsonl`, `config/network.yml`, `config/sensors.yml` не хранятся в git.

## Корень

- `.dockerignore` - исключает секреты, runtime-логи, generated-сенсоры и кэш из Docker build context.
- `.gitignore` - не дает случайно закоммитить `.env`, логи, generated-файлы сенсоров и локальные дампы документации.
- `README.md` - главный вход: что это за проект, как запустить центр, как поставить сенсор.
- `archive/web-manager-frontend/` - отложенный web-интерфейс. Он сохранен для будущей переработки, но сейчас не участвует в работе центра.

## Конфигурация

- `config/project.json` - единственный tracked источник настройки стенда: сеть, центр, сенсоры, Cowrie, порты, маскировка.

## Центр

- `center/__init__.py` - делает `center` Python-пакетом, чтобы backend и generator могли импортировать общий каталог.
- `center/docker-compose.yml` - Docker stack центра: collector на `8080`, API-manager на `8090`.

## Collector

- `center/collector/Dockerfile` - образ центрального приемника событий.
- `center/collector/server.py` - HTTP API collector: принимает события, хранит JSONL, отдает `/health`, `/api/events`, `/api/sensors`; понимает `sensor.status` и показывает версию, сервисы и порты сенсора.

## Manager

- `center/manager/Dockerfile` - образ API-manager с Ansible, генератором и исходниками сенсора.
- `center/manager/backend/server.py` - API-manager: читает/сохраняет проект, валидирует конфиг, запускает генерацию и Ansible jobs.

## Каталог Honeypot

- `center/honeypots/__init__.py` - пакет для общего каталога honeypot.
- `center/honeypots/catalog.py` - справочник реально поддержанных приманок. Сейчас там Cowrie, его сервисы SSH/Telnet, host-порты и поля настроек.

## Генератор

- `center/orchestrator/generate.py` - превращает `config/project.json` в ignored-папку `sensors/<name>/`: `.env`, `docker-compose.yml`, `cowrie.cfg`, `userdb.txt`, `honeyfs`, runtime-директории.

## Ansible

- `center/ansible/deploy_sensor.yml` - playbook установки сенсора по SSH: ставит Docker/Compose, останавливает старый EDC compose stack сенсора, удаляет leftover-контейнеры этого сенсора, копирует runtime/generated-конфиг и запускает новый `edc_<sensor>` compose project.

## Sensor

- `sensor/Dockerfile` - единый образ сенсора `edc-sensor`; собирает Cowrie из исходников в Python venv, чтобы поддерживать ARM-платы.
- `sensor/runtime/entrypoint.py` - стартует внутри одного контейнера Cowrie, sensor-node, log-agent и display-agent.
- `sensor/runtime/sensor_node.py` - управляемый слой сенсора: status heartbeat, локальный state, список портов/сервисов и раннее событие `sensor.connection_seen` по `/proc/net/tcp`.
- `sensor/runtime/log_agent.py` - читает `cowrie.json` и отправляет события в центр, не теряя их при временной недоступности collector.
- `sensor/runtime/display_agent.py` - печатает локальный статус сенсора и связь с центром.

## Scripts

- `scripts/install_central.sh` - установка Docker/Compose и запуск центра.
- `scripts/deploy_sensor.sh` - CLI-обертка над manager API для установки/обновления сенсора по SSH без web-интерфейса.
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
- `docs/honeypot_installation.md` - как центр устанавливает и настраивает honeypot на сенсоре.
- `docs/masking.md` - краткие тезисы по deception-маскировке.
- `docs/thesis_notes.md` - заметки для ВКР.
- `docs/archive/web_configurator.md` - старая документация web-конфигуратора, оставлена как архив.
