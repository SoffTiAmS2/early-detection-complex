# Functions, Inputs And Outputs

Документ описывает, что делает каждая основная часть комплекса, какие данные принимает и что отдает наружу.

## Web Manager

Файл: `center/manager/backend/server.py`

### `GET /api/health`

Назначение: проверить, что web-manager запущен.

Ввод: нет.

Вывод:

```json
{
  "status": "ok",
  "project": "/app/config/project.json",
  "jobs": []
}
```

### `GET /api/catalog`

Назначение: отдать справочник honeypot, их сервисов и настроек для интерфейса.

Ввод: нет.

Вывод:

- `honeypots` - дерево доступных honeypot;
- `services` - справочник протоколов, которые может включать honeypot.

### `GET /api/project`

Назначение: прочитать текущую конфигурацию комплекса.

Ввод: нет.

Вывод: содержимое `config/project.json`.

### `PUT /api/project`

Назначение: сохранить конфигурацию сети, сенсоров, honeypot, сервисов, настроек и маскировки.

Ввод: JSON-проект:

- `network.subnet` - подсеть стенда;
- `network.gateway` - шлюз;
- `network.central_node` - IP центра;
- `sensors[].name` - безопасное имя сенсора;
- `sensors[].host` - IP сенсорной платы;
- `sensors[].role` - логическая роль;
- `sensors[].honeypots[]` - выбранные honeypot;
- `sensors[].honeypots[].services[]` - сервисы внутри выбранного honeypot;
- `sensors[].honeypots[].settings` - настройки конкретного honeypot;
- `sensors[].mask` - deception-легенда узла.

Вывод:

```json
{"status": "saved"}
```

Ошибки: `400`, если имя сенсора небезопасно, выбран неизвестный honeypot, сервис не относится к выбранному honeypot или настройка не поддерживается.

### `POST /api/generate`

Назначение: сгенерировать ignored-файлы сенсоров из `config/project.json`.

Ввод: нет.

Вывод:

- `ok` - успешно или нет;
- `returncode` - код завершения генератора;
- `stdout` - что создано;
- `stderr` - текст ошибки.

### `POST /api/deploy-sensor`

Назначение: запустить фоновую установку или обновление выбранного сенсора по SSH.

Ввод:

```json
{
  "sensor": "sensor1",
  "ssh_host": "192.168.0.128",
  "ssh_port": 22,
  "ssh_user": "root",
  "ssh_password": "password",
  "become_password": "password"
}
```

Вывод: `202 Accepted` и объект job.

Пароли используются только для текущего запуска Ansible и не сохраняются в `config/project.json`.

### `GET /api/jobs`

Назначение: список последних задач установки.

Ввод: нет.

Вывод: массив jobs с `id`, `sensor`, `status`, `step`, `progress`, `output`.

### `GET /api/jobs/<id>`

Назначение: получить прогресс конкретной установки.

Ввод: `id` задачи в URL.

Вывод: один job.

### `POST /api/jobs/<id>/cancel`

Назначение: остановить текущий Ansible-запуск.

Ввод: `id` задачи в URL.

Вывод:

```json
{"status": "cancelled", "job": {}}
```

### `GET /api/center/status`

Назначение: показать состояние collector и сенсоров в интерфейсе manager.

Ввод: нет.

Вывод:

- `central_url` - URL collector;
- `collector` - ответ `/health`;
- `collector_error` - ошибка связи, если есть;
- `sensors` - сенсоры, от которых уже приходили события;
- `sensors_error` - ошибка чтения сенсоров, если есть.

## Collector

Файл: `center/collector/server.py`

### `GET /health`

Назначение: проверить collector.

Вывод:

```json
{"status": "ok", "events": 10}
```

### `GET /api/events?limit=100`

Назначение: получить последние события.

Ввод:

- `limit` - число от `1` до `1000`.

Вывод:

```json
{"events": []}
```

### `POST /api/events`

Назначение: принять событие от log-agent.

Ввод: JSON-событие.

Вывод: `202 Accepted`.

### `GET /api/sensors`

Назначение: агрегировать последние события по сенсорам.

Вывод:

```json
{"sensors": [{"sensor": "sensor1", "events": 3, "last_type": "payload"}]}
```

## Generator

Файл: `center/orchestrator/generate.py`

Назначение: из `config/project.json` создать ignored-директорию `sensors/<name>/`.

Ввод:

- tracked `config/project.json`;
- справочник `center/honeypots/catalog.py`.

Вывод:

- `sensors/<name>/.env`;
- `sensors/<name>/docker-compose.yml`;
- `sensors/<name>/cowrie/etc/cowrie.cfg`;
- `sensors/<name>/README.md`;
- ignored `config/network.yml` и `config/sensors.yml` для совместимости.

## Sensor Runtime

### `cowrie`

Образ: единый `edc-sensor`, собирается из `sensor/Dockerfile` на базе `cowrie/cowrie:latest`.

Ввод:

- `cowrie/etc/cowrie.cfg`;
- host-port mappings из `docker-compose.yml`.

Что делает:

- запускает настоящий Cowrie SSH/Telnet honeypot;
- пишет JSON-события в `logs/cowrie.json`;
- сохраняет скачанные артефакты в `cowrie/downloads`.

Вывод: `logs/cowrie.json`.

### `log-agent`

Файл: `sensor/runtime/log_agent.py`

Ввод:

- `/cowrie/cowrie-git/var/log/cowrie/cowrie.json`;
- `CENTRAL_URL=http://<center>:8080/api/events`.

Что делает:

- читает события;
- отправляет их в collector;
- не считает событие доставленным, если POST неуспешен;
- повторяет отправку с backoff.

Вывод: HTTP POST в collector.

### `display-agent`

Файл: `sensor/runtime/display_agent.py`

Ввод:

- `CENTRAL_HEALTH_URL`;
- env сенсора.

Что делает: периодически печатает локальный статус сенсора и связи с центром.
