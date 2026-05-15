# Центр

Центр оформлен как отдельное серверное Python-приложение. Основная точка входа: `center/main.py`.

Структура:

- `main.py` - CLI entrypoint.
- `app.py` - создание HTTP-сервера.
- `api/handler.py` - REST API и маршруты веб-интерфейса.
- `core/policy.py` - политика сенсоров и desired-state.
- `core/overview.py` - сводка состояния сенсоров и событий.
- `core/paths.py`, `core/utils.py` - общие пути и утилиты.
- `persistence/events.py` - события (PostgreSQL по умолчанию, SQLite fallback).
- `server.py` - совместимый wrapper для старой команды запуска.

Функции:

- API control-plane со встроенным HTML-интерфейсом `/settings`;
- установка/обновление сенсоров через Ansible playbooks;
- хранение рабочей политики `config/site.local.json`;
- синхронизация сенсоров через один endpoint: статус на входе, desired state на выходе;
- приём raw events из honeypot runtime;
- хранение событий в PostgreSQL (`CENTER_DB_DSN`), SQLite используется только как fallback;
- настройка honeypot-модулей, сервисов и host-портов.

Основные API:

```text
GET  /
GET  /health
GET  /api/overview
GET  /api/modules
GET  /api/profiles
GET  /api/policy
GET  /api/sensors
POST /api/sensors
POST /api/sensors/<id>/apply-profile
POST /api/sensors/<id>/sync
PATCH /api/sensors/<id>/modules/<module_id>
DELETE /api/sensors/<id>?purge_events=1
POST /api/events
GET  /api/events
GET  /api/db/stats
POST /api/db/purge
```

Запуск:

```sh
python3 -m center.main --host 0.0.0.0 --port 8080
```

При первом запуске `config/site.local.json` создаётся из `config/site.example.json`.
Административную авторизацию можно включить переменными `CENTER_AUTH_USER` и `CENTER_AUTH_PASSWORD` или `CENTER_AUTH_TOKEN`.
Подключение к PostgreSQL задаётся переменной `CENTER_DB_DSN`.

Также доступен короткий запуск:

```sh
python3 -m center --host 0.0.0.0 --port 8080
```
