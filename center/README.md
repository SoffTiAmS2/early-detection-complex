# Центр

Центр оформлен как отдельное серверное Python-приложение. Основная точка входа: `center/main.py`.

Структура:

- `main.py` - CLI entrypoint.
- `app.py` - создание HTTP-сервера.
- `api/handler.py` - REST API и маршруты веб-интерфейса.
- `core/policy.py` - политика сенсоров и desired-state.
- `core/overview.py` - сводка состояния для dashboard.
- `core/paths.py`, `core/utils.py` - общие пути и утилиты.
- `persistence/events.py` - SQLite-события.
- `services/installer.py` - SSH-установка сенсора и журнал прогресса.
- `web/views.py`, `web/templates/` - HTML-интерфейс.
- `server.py` - совместимый wrapper для старой команды запуска.

Функции:

- веб-интерфейс на русском языке;
- установка/обновление сенсора по SSH из формы в центре;
- хранение рабочей политики `config/site.local.json`;
- синхронизация сенсоров через один endpoint: статус на входе, desired state на выходе;
- приём raw events из honeypot runtime;
- хранение событий в SQLite `var/center/events.sqlite3`;
- настройка honeypot-модулей, сервисов и host-портов.

Основные API:

```text
GET  /
GET  /health
GET  /api/overview
GET  /api/modules
GET  /api/policy
GET  /api/sensors
POST /api/sensors
POST /api/sensors/<id>/sync
PATCH /api/sensors/<id>/modules/<module_id>
POST /api/install-sensor
GET  /api/install-sensor
GET  /api/install-sensor/<job_id>
POST /api/install-sensor/<job_id>/cancel
POST /api/events
GET  /api/events
```

Запуск:

```sh
python3 -m center.main --host 0.0.0.0 --port 8080
```

При первом запуске `config/site.local.json` создаётся из `config/site.example.json`.
Административную авторизацию можно включить переменными `CENTER_AUTH_USER` и `CENTER_AUTH_PASSWORD` или `CENTER_AUTH_TOKEN`.

Также доступен короткий запуск:

```sh
python3 -m center --host 0.0.0.0 --port 8080
```
