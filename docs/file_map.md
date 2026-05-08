# File Map

## Root

- `README.md` - новый главный вход в проект.
- `.gitignore` - исключает runtime, generated и секреты.
- `.dockerignore` - исключает архивы и runtime из будущих Docker build contexts.

## New Architecture

- `center/README.md` - назначение будущего control-plane.
- `center/server.py` - минимальный MVP control-plane: modules, sensors, desired-state, events; хранит события в SQLite с сохранением полного `raw_event`.
- `sensor/README.md` - назначение будущего managed sensor appliance.
- `sensor/agent.py` - managed sensor-agent: polling desired-state, Docker runtime apply, status event.
- `sensor/runtime.py` - Docker Compose runtime: запускает реальные honeypot images, чистит старые контейнеры комплекса и собирает raw container logs.
- `catalog/README.md` - правила добавления honeypot-модулей.
- `catalog/honeypots.json` - первичный registry модулей: Cowrie, OpenCanary, Heralding, Conpot, Dionaea.
- `config/site.example.json` - пример политики стенда и desired state сенсора.
- `tools/validate_policy.py` - проверяет, что site-policy ссылается только на существующие modules/services и не конфликтует по host ports.
- `scripts/run_mvp.sh` - запускает локальную демонстрацию center + sensor-agent.
- `scripts/run_sensor_runtime.sh` - запускает sensor-agent в режиме Docker honeypot runtime.

## Docs

- `docs/architecture.md` - целевая архитектура.
- `docs/references.md` - open-source reference systems.
- `docs/roadmap.md` - порядок реализации.
- `docs/test_stand.md` - проверка текущего стенда center/sensor1 в сети `192.168.0.0/24`.
- `docs/file_map.md` - этот файл.

## Archive

- `archive/prototype-v0/` - старый рабочий прототип Cowrie/Ansible/API.
- `archive/prototype-v0/README.md` - что сохранено и почему.
