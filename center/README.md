# Центр

`center/server.py` - единый control-plane комплекса.

Функции:

- веб-интерфейс на русском языке;
- установка/обновление сенсора по SSH из формы в центре;
- хранение политики `config/site.example.json`;
- выдача desired-state сенсорам;
- приём enroll/status/raw events;
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
GET  /api/sensors/<id>/desired-state
PATCH /api/sensors/<id>/modules/<module_id>
POST /api/install-sensor
GET  /api/install-sensor
GET  /api/install-sensor/<job_id>
POST /api/install-sensor/<job_id>/cancel
POST /api/enroll
POST /api/events
GET  /api/events
```

Запуск:

```sh
python3 center/server.py --host 0.0.0.0 --port 8080
```
