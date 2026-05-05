# Center Control-Plane

Новая версия центра должна быть control-plane, а не просто web/API-оберткой над Ansible.

## Responsibilities

- sensor registry;
- module registry;
- desired state API;
- event ingest API;
- update history;
- enrollment/bootstrap;
- future operator UI.

## API Sketch

```text
POST /api/enroll
GET  /api/sensors
GET  /api/sensors/<id>/desired-state
PUT  /api/sensors/<id>/desired-state
POST /api/events
GET  /api/modules
GET  /api/updates
```

## Rule

Центр хранит желаемое состояние. Сенсор сам применяет это состояние и сообщает результат.
