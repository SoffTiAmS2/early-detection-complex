# Roadmap

## Stage 0: Archive Prototype

Status: in progress.

- Старый Cowrie/Ansible/API prototype сохранен в `archive/prototype-v0/`.
- Новый корень проекта освобожден под architecture-first реализацию.

## Stage 1: Module Catalog

Goal: описать реальные модули до реализации UI.

- `catalog/honeypots.json`;
- module contract;
- resource classes;
- service/port model;
- supported architecture model.

Первый порядок:

1. Cowrie.
2. OpenCanary.
3. Heralding.
4. Conpot.
5. Dionaea.

## Stage 2: Sensor Agent

Goal: заменить прямой Ansible runtime на managed sensor node.

Status: MVP skeleton started.

Sensor-agent должен:

- зарегистрироваться в центре;
- polling-ом получать desired state;
- ставить/обновлять modules;
- запускать module runner;
- слать `sensor.status`;
- слать normalized events;
- делать rollback при неудачном применении state.

Сейчас `sensor/agent.py` уже делает polling desired state, dry-run apply, локальный `applied_state.json` и отправку `sensor.status`.

## Stage 3: Center Control-Plane

Goal: центр должен управлять сенсорами как fleet.

Status: MVP skeleton started.

Нужно:

- sensor registry;
- desired state storage;
- module registry API;
- event ingest;
- job/update history;
- enrollment/bootstrap endpoint.

Сейчас `center/server.py` уже отдает module catalog, sensor list, desired state и принимает events/enroll events.

## Stage 4: First Real Modules

Goal: не добавлять fake пункты.

Для Cowrie:

- перенести проверенную сборку из `archive/prototype-v0/`;
- оставить honeyfs/userdb/persona;
- нормализовать события.

Для OpenCanary:

- проверить официальный способ установки;
- сделать config template;
- включить HTTP/FTP/Redis/MySQL как первые легкие сервисы;
- написать event adapter.

## Stage 5: Operator UI

UI возвращается только после того, как есть нормальная модель:

- sensors;
- desired state;
- modules;
- services;
- status;
- events;
- updates/rollback.
