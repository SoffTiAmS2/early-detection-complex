# Early Detection Complex

Новая ветка проекта строится как распределенный комплекс раннего обнаружения подозрительной сетевой активности.

Старый рабочий прототип с Cowrie, manager API, Ansible и web-архивом сохранен в `archive/prototype-v0/`. Он больше не считается основной архитектурой, но остается как источник проверенных кусков: сборка Cowrie на ARM, доставка событий, Ansible-деплой и generated-конфигурация.

## Новый Вектор

Берем архитектурные идеи из open-source deception-платформ:

- HoneySens: центр управляет сенсорами, сенсоры получают конфигурацию и обновления от сервера.
- T-Pot CE: большой каталог honeypot и sensor/hive-модель как референс, но без тяжелого ELK-комбайна в первом этапе.
- OpenCanary: легкий multi-protocol honeypot как первый кандидат после Cowrie.
- Cowrie: качественная SSH/Telnet deception.

## Целевая Структура

```text
center/               # control-plane: API, registry, policies, events
sensor/               # appliance-agent: polling, module runtime, status, update/rollback
catalog/              # specs honeypot-модулей и профилей deception
config/               # пример политики стенда
docs/                 # новая архитектура и roadmap
archive/prototype-v0/ # старый рабочий прототип, сохранен без удаления
```

## Принцип

Сенсорная плата должна требовать минимум ручной работы:

```text
ОС + сеть + SSH + регистрация в центре
```

Дальше центр должен:

- зарегистрировать сенсор;
- выдать ему desired state;
- подготовить нужные honeypot-модули;
- управлять портами, профилем и deception-данными;
- получать события, status heartbeat и health;
- обновлять sensor runtime и honeypot-модули;
- откатывать неудачные обновления.

## Первый Рабочий Runtime

1. Описать каталог модулей: Cowrie, OpenCanary, Heralding, Conpot, Dionaea.
2. Сделать единый sensor manifest: какие modules включены, какие ports слушают, куда слать события.
3. Сделать lightweight sensor-agent, который polling-ом забирает desired state с центра.
4. Запускать реальные upstream Docker images через sensor Docker runtime.
5. Удалять старые контейнеры комплекса перед применением новой конфигурации.
6. Собирать raw logs контейнеров и отправлять их в центр.

## Проверка Новой Политики

Пока это не runtime, но уже есть проверяемая модель каталога и desired state:

```sh
tools/validate_policy.py
```

Валидатор проверяет, что `config/site.example.json` использует только существующие modules/services из `catalog/honeypots.json` и не содержит конфликтов host ports на одном сенсоре.

## Control Loop

Уже есть базовая HoneySens-like модель: центр хранит desired state, а сенсор сам его забирает, применяет локально и докладывает состояние.

```sh
scripts/run_mvp.sh
```

Что он показывает:

1. Запускает `center/server.py`.
2. `sensor/agent.py` регистрируется через `POST /api/enroll`.
3. `sensor/agent.py` забирает `GET /api/sensors/sensor1/desired-state`.
4. Агент строит локальный dry-run plan по Cowrie/OpenCanary.
5. Агент пишет `var/sensor/applied_state.json`.
6. Агент отправляет `sensor.status` в `POST /api/events`.
7. Центр показывает обзор через `GET /api/overview` и sensor summary через `GET /api/sensors`.

Ручной запуск:

```sh
python3 center/server.py --host 127.0.0.1 --port 8080
python3 sensor/agent.py --center http://127.0.0.1:8080 --sensor-id sensor1 --once
curl http://127.0.0.1:8080/api/sensors
```

`--once` показывает control loop без открытия портов. Для реального раннего обнаружения sensor-agent запускается в Docker runtime:

```sh
python3 sensor/agent.py --center http://192.168.0.196:8080 --sensor-id sensor1 --serve
```

В этом режиме сенсор создает `var/sensor/docker-runtime/docker-compose.yml`, удаляет старые контейнеры с label `edc.sensor_id=<sensor_id>` и запускает реальные Docker images:

```text
Cowrie     cowrie/cowrie:latest
OpenCanary thinkst/opencanary:latest
Dionaea    dinotools/dionaea:latest
Conpot     honeynet/conpot:latest
Heralding  dtagdevsec/heralding:24.04.1
```

Sensor-agent не эмулирует протоколы сам. Он только оркестрирует контейнеры, читает `docker logs` и отправляет сырые события контейнеров в центр.

События центра хранятся в SQLite (`var/center/events.sqlite3`). Для каждого события сохраняются нормализованные поля для фильтрации и dashboard, а полный оригинальный JSON лежит в поле `raw_event`. MITRE-поля в логи не добавляются: они должны вычисляться отдельным аналитическим слоем, а не портить исходную телеметрию honeypot.

## Текущий Тестовый Стенд

`config/site.example.json` настроен под текущую лабораторную пару:

```text
center  - 192.168.0.196:8080
sensor1 - 192.168.0.173
```

Проверка на двух машинах описана в `docs/test_stand.md`.

Основные API центра:

```text
GET  /
GET  /honeypots/<module_id>
GET  /health
GET  /api/overview
GET  /api/modules
GET  /api/sensors
POST /api/sensors
GET  /api/sensors/<id>/desired-state
PUT  /api/policy
PATCH /api/sensors/<id>/modules/<module_id>
PATCH /api/sensors/<id>/modules/<module_id>/services/<service_id>
POST /api/enroll
POST /api/events
GET  /api/events
```

`GET /` открывает живой dashboard центра: состояние сенсоров, running-модули, severity/module/service counters, последние события раннего обнаружения и список реально прописанных honeypot-модулей.
Отдельная страница `GET /honeypots/<module_id>?sensor_id=sensor1` настраивает конкретный honeypot: включение модуля, включение сервисов, host-порты и schema-driven settings. Изменения сохраняются через manager API, версия policy увеличивается, а sensor-agent применяет ее на следующем polling loop без ручного рестарта.

Проверка живого reconfigure:

```sh
tools/e2e_reconfigure_test.py
```

Тест поднимает временный центр, проверяет PATCH API и материализацию Docker Compose без запуска тяжелых upstream images.

Текущая политика включает несколько модулей одновременно:

```text
Cowrie:     ssh 2222, telnet 2223
OpenCanary: http 8081, ftp 2121, redis 6379, mysql 3306
Heralding:  ftp 2122, http 8082, pop3 1110, smtp 2525
Conpot:     modbus 1502, http 8800
Dionaea:    smb 1445, http 8083, ftp 2123
```

В каталоге больше нет “витринных” honeypot-пунктов. Там остаются только модули, которые реально описаны в текущей policy и могут быть применены sensor-agent: Cowrie, OpenCanary, Heralding, Conpot и Dionaea.

## Где Старый Код

Проверенный прототип находится здесь:

```text
archive/prototype-v0/
```

Он нужен как reference implementation, но новый код должен расти в корневых `center/`, `sensor/`, `catalog/`, `config/` и `docs/`.
