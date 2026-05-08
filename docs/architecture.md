# Architecture

## Цель

Построить легкую deception-платформу раннего обнаружения, где центр управляет множеством сенсоров, а каждый сенсор может запускать несколько honeypot-модулей.

## Модель

```text
center control-plane
├─ sensor registry
├─ desired state API
├─ module registry
├─ event ingest
├─ update registry
└─ operator API/UI

sensor appliance
├─ enrollment/bootstrap
├─ polling control-agent
├─ module runner
├─ event pipeline
├─ local health/state
└─ update/rollback

honeypot modules
├─ cowrie
├─ opencanary
├─ heralding
├─ conpot
└─ dionaea
```

## Почему Так

Старый вариант через прямой Ansible-запуск удобен для первого стенда, но плохо масштабируется. Правильнее сделать сенсор автономным managed node:

- центр хранит desired state;
- сенсор сам периодически спрашивает центр, что должно быть запущено;
- сенсор применяет изменения локально;
- сенсор сообщает status, health, version и events;
- центр не обязан держать постоянный SSH-сеанс до каждой платы.

SSH остается только bootstrap-механизмом: поставить sensor-agent первый раз или восстановить сломанную плату.

## Event Flow

```text
attacker -> honeypot module -> local event adapter -> sensor event pipeline -> center ingest
```

Каждое событие должно приводиться к общей схеме:

```json
{
  "sensor_id": "sensor1",
  "module": "cowrie",
  "service": "ssh",
  "event_type": "login.success",
  "src_ip": "192.168.0.55",
  "dst_port": 2222,
  "severity": "high",
  "timestamp": "2026-05-05T00:00:00Z",
  "raw_event": {}
}
```

Центр хранит события в SQLite. Нормализованные поля (`sensor_id`, `module`, `service`, `event_type`, `src_ip`, `dst_port`, `severity`) используются для фильтрации и dashboard, а полный исходный JSON события сохраняется в `raw_event`. В сами логи не добавляются `mitre_techniques`: сопоставление с MITRE и корреляция должны быть отдельным аналитическим слоем поверх сохраненных оригинальных событий.

## Desired State

Desired state - это не generated compose, а декларация:

```json
{
  "sensor_id": "sensor1",
  "version": 12,
  "modules": [
    {
      "id": "cowrie",
      "enabled": true,
      "services": [{"id": "ssh", "host_port": 2222}]
    }
  ]
}
```

Sensor-agent превращает эту декларацию в локальные контейнеры, конфиги, ports и health checks.

## Module Contract

Каждый honeypot-модуль обязан иметь:

- module id;
- список сервисов и портов;
- config schema;
- container/build recipe;
- event adapter;
- health check;
- smoke test;
- resource class;
- supported architectures.

Без этого модуль не попадает в рабочий каталог, даже если он красивый в UI.

## Current MVP

Текущий минимальный MVP уже реализует control loop:

- `center/main.py` - точка входа control-plane на Python stdlib;
- `center/api/handler.py`, `center/core/policy.py`, `center/persistence/events.py`, `center/services/installer.py` - разделенные компоненты центра;
- `sensor/agent.py` - polling sensor-agent;
- `scripts/run_mvp.sh` - локальная демонстрация одного цикла;
- `tools/validate_policy.py` - проверка site-policy против module catalog.

В текущем MVP центр также отдает `/api/overview`, проверяет политику перед выдачей desired state и принимает `sensor.enroll`. Sensor-agent отправляет enrollment, пишет локальное applied state и отправляет расширенный `sensor.status` с версией агента, профилем, active-модулями и портами.

В режиме `--serve` sensor-agent запускает Docker runtime: генерирует compose-файл, удаляет старые контейнеры с label `edc.sensor_id`, стартует реальные upstream/community images Cowrie, OpenCanary, Dionaea, Conpot и Heralding, затем отправляет status и raw container logs в центр.

Центр не должен подменять исходные события своей аналитикой. Raw telemetry сохраняется как `raw_event`; нормализация нужна только для фильтрации, поиска и dashboard. Корреляция, risk-score и MITRE-техники должны вычисляться отдельным аналитическим слоем поверх сохраненных исходных логов.
