# Дорожная Карта

## Этап 0: Архивировать Прототип

Статус: в работе.

- Старый Cowrie/Ansible/API prototype сохранен в `archive/prototype-v0/`.
- Новый корень проекта освобожден под реализацию от архитектуры.

## Этап 1: Каталог Модулей

Цель: описать реальные модули до реализации UI.

- `catalog/honeypots.json`;
- контракт модуля;
- классы ресурсов;
- модель сервисов и портов;
- модель поддержанных архитектур.

Первый порядок:

1. Cowrie.
2. OpenCanary.
3. Heralding.
4. Conpot.
5. Dionaea.

## Этап 2: Агент Сенсора

Цель: заменить прямой Ansible runtime на управляемый сенсор.

Статус: MVP-каркас начат.

Sensor-agent должен:

- зарегистрироваться в центре;
- polling-ом получать desired state;
- ставить/обновлять модули;
- запускать module runner;
- слать `sensor.status`;
- слать нормализованные события;
- делать rollback при неудачном применении state.

Сейчас `sensor/agent.py` уже делает polling desired state, dry-run apply, локальный `applied_state.json` и отправку `sensor.status`.

## Этап 3: Control Plane Центра

Цель: центр должен управлять сенсорами как парком узлов.

Статус: MVP-каркас начат.

Нужно:

- реестр сенсоров;
- хранение desired state;
- module registry API;
- приём событий;
- история задач и обновлений;
- sensor sync/bootstrap endpoint.

Сейчас `center/main.py` запускает центр, а `center/api/handler.py` отдает module catalog, sensor list, принимает sensor sync и raw events.

## Этап 4: Первые Реальные Модули

Цель: не добавлять фиктивные пункты.

Для Cowrie:

- перенести проверенную сборку из `archive/prototype-v0/`;
- оставить honeyfs/userdb/persona;
- нормализовать события.

Для OpenCanary:

- проверить официальный способ установки;
- сделать шаблон конфига;
- включить HTTP/FTP/Redis/MySQL как первые легкие сервисы;
- написать event adapter.

## Этап 5: Операторский UI

UI возвращается только после того, как есть нормальная модель:

- сенсоры;
- desired state;
- модули;
- сервисы;
- status;
- события;
- updates/rollback.
