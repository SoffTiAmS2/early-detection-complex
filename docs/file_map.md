# File Map

## Root

- `README.md` - новый главный вход в проект.
- `.gitignore` - исключает runtime, generated и секреты.
- `.dockerignore` - исключает архивы и runtime из будущих Docker build contexts.

## New Architecture

- `center/README.md` - назначение будущего control-plane.
- `sensor/README.md` - назначение будущего managed sensor appliance.
- `catalog/README.md` - правила добавления honeypot-модулей.
- `catalog/honeypots.json` - первичный registry модулей: Cowrie, OpenCanary, Heralding, Conpot, Dionaea.
- `config/site.example.json` - пример политики стенда и desired state сенсора.
- `tools/validate_policy.py` - проверяет, что site-policy ссылается только на существующие modules/services и не конфликтует по host ports.

## Docs

- `docs/architecture.md` - целевая архитектура.
- `docs/references.md` - open-source reference systems.
- `docs/roadmap.md` - порядок реализации.
- `docs/file_map.md` - этот файл.

## Archive

- `archive/prototype-v0/` - старый рабочий прототип Cowrie/Ansible/API.
- `archive/prototype-v0/README.md` - что сохранено и почему.
