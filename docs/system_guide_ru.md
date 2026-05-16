# Early Detection Complex: единая документация проекта

Документ описывает текущую реализацию распределенного комплекса раннего выявления подозрительной сетевой активности. Это единственный основной файл документации: архитектура, структура каталогов, профильная модель, сборка Docker-образов, запуск, API, диагностика и дальнейший план собраны здесь.

Файл `ВКРТекст.md` не является частью инженерной документации и не должен редактироваться при рефакторинге кода.

## 1. Идея проекта

Комплекс состоит из центра управления и сенсоров.

Центр:

- хранит политику сенсоров;
- хранит каталог профилей маскировки устройств;
- превращает профиль устройства в `desired_state`;
- принимает события и статус сенсоров;
- показывает UI администратора;
- хранит события в PostgreSQL, если задан `CENTER_DB_DSN`, иначе использует SQLite;
- хранит последний технический статус сенсора отдельно от журнала событий;
- поднимает Grafana для быстрого просмотра событий, профилей и состояния сенсоров.

Сенсор:

- получает `desired_state` от центра;
- генерирует `docker-compose.yml` и конфиги honeypot-контейнеров;
- запускает реальные honeypots через Docker Compose;
- собирает логи контейнеров;
- отправляет нормализованные события и статус в центр.

Главное изменение текущего этапа: администратор выбирает не контейнер `cowrie` или `glutton`, а профиль маскировки устройства: принтер, камера, роутер, backup server, Linux server и так далее.

## 2. Текущий стек honeypots

Активный стек проекта:

| Honeypot | Назначение |
|---|---|
| Cowrie | SSH/Telnet-приманка |
| Glutton | универсальная TCP/UDP-приманка для произвольных портов |
| HoneyPy | легкие web-панели и простые сервисы |
| Conpot | ICS/SCADA-приманки |
| Mailoney | SMTP-приманка |

Старый стек `opencanary`, `dionaea`, `heralding` не является активным направлением текущей реализации.

## 3. Главная сущность: DeviceMaskProfile

Профиль маскировки устройства описывает не контейнер, а легенду узла в сети.

Структура профиля:

```text
DeviceMaskProfile
├── id
├── name
├── title
├── device_type
├── description
├── legend
├── exposed_ports
├── honeypots
├── banners
├── service_fingerprints
├── docker_template
├── config_templates
├── resource_limits
├── logging
└── detection_goals
```

Каталог профилей находится в файле:

```text
catalog/device_mask_profiles.json
```

Каталог технических возможностей honeypot-модулей находится в файле:

```text
catalog/honeypots.json
```

Центр берет профиль из `device_mask_profiles.json`, проверяет его по `honeypots.json` и строит из него обычный `desired_state`, который понимает агент.

## 4. Готовые профили

Сейчас в каталоге реализованы 10 профилей:

| ID | Название | Назначение |
|---|---|---|
| `printer` | Принтер | HP LaserJet / JetDirect / Web Panel / SNMP |
| `scanner` | Сканер / МФУ | Canon/Xerox/Epson-like, web login, FTP, SNMP |
| `ip-camera` | IP-камера | RTSP, HTTP admin panel, Telnet, discovery |
| `router` | Роутер | SSH, Telnet, HTTP admin, SNMP, Winbox-like |
| `backup-server` | Backup Server | SSH, FTP, rsync, NFS-like, SMB-like, web panel |
| `workstation` | Рабочая станция | SMB/RDP/WinRM-like ports |
| `linux-server` | Linux Server | SSH, HTTP, FTP, MySQL, PostgreSQL, Redis |
| `mail-server` | Mail Server | SMTP, POP3, IMAP, relay/credential probes |
| `industrial-controller` | Industrial Controller | Modbus, S7, SNMP, EtherNet/IP-like |
| `nas-storage` | NAS Storage | SMB, NFS, AFP, web management, SSH |

Пример: профиль `ip-camera` открывает порты `80`, `554`, `8000`, `8080`, `8899`, `23` и использует `cowrie`, `glutton`, `honeypy`.

Пример: профиль `printer` открывает `80`, `443`, `515`, `631`, `9100`, `161/udp` и использует `glutton`, `honeypy`.

## 5. Как центр превращает профиль в desired_state

Администратор выбирает профиль:

```json
{
  "sensor_id": "banana-pi-pro-1",
  "active_profile": "ip-camera"
}
```

Центр строит `desired_state`:

```json
{
  "runtime_mode": "docker",
  "active_profile": "ip-camera",
  "config_version": 17,
  "device_type": "ip-camera",
  "exposed_ports": [
    { "port": 80, "honeypot": "honeypy", "module_service": "http" },
    { "port": 554, "honeypot": "glutton", "module_service": "rtsp" },
    { "port": 23, "honeypot": "cowrie", "module_service": "telnet" }
  ],
  "services": [
    {
      "name": "cowrie",
      "enabled": true,
      "ports": { "23": "telnet" },
      "template": "camera-telnet"
    },
    {
      "name": "glutton",
      "enabled": true,
      "ports": { "554": "rtsp", "8000": "camera_service", "8899": "discovery" },
      "template": "camera-rtsp-and-discovery"
    },
    {
      "name": "honeypy",
      "enabled": true,
      "ports": { "80": "http", "8080": "http_alt" },
      "template": "fake-camera-web"
    }
  ],
  "modules": []
}
```

Поле `services` нужно для человекочитаемой логики и UI. Поле `modules` нужно агенту и Docker-runtime. Оно заполняется тем же renderer-ом.

Код renderer-а находится здесь:

```text
center/core/profiles.py
```

## 6. Страницы центра

Текущие страницы:

| Страница | URL | Назначение |
|---|---|---|
| Dashboard / Settings | `/` | сенсоры, модули, события, ручная настройка |
| Профили маскировки | `/profiles` | выбор устройства: Printer, IP Camera, Router и т.д. |
| Техническая маскировка | `/mask` | низкоуровневые настройки баннеров старого типа |
| База | `/db` | статистика и очистка событий |

Страница `/profiles` является основной для новой модели. Там администратор выбирает сенсор и применяет к нему профиль устройства.

## 7. API центра

Основные API:

| Метод | Маршрут | Назначение |
|---|---|---|
| `GET` | `/health` | состояние центра |
| `GET` | `/api/device-mask-profiles` | каталог DeviceMaskProfile |
| `GET` | `/api/profiles` | совместимый alias для каталога профилей |
| `GET` | `/api/policy` | текущая политика |
| `GET` | `/api/sensors` | сенсоры и статус |
| `POST` | `/api/sensors` | добавить сенсор |
| `POST` | `/api/sensors/<id>/apply-profile` | применить профиль к сенсору |
| `PATCH` | `/api/sensors/<id>/modules/<module>` | ручное изменение модуля |
| `POST` | `/api/sensors/<id>/sync` | sync endpoint агента |
| `POST` | `/api/events` | прием событий |
| `GET` | `/api/events` | чтение событий |

Применить профиль через API:

```bash
curl -X POST http://127.0.0.1:8080/api/sensors/banana-pi-pro-1/apply-profile \
  -H 'Content-Type: application/json' \
  -d '{"profile_id":"ip-camera"}'
```

Получить каталог профилей:

```bash
curl http://127.0.0.1:8080/api/device-mask-profiles
```

## 8. Логика работы агента

Основной цикл агента:

```text
loop:
  POST /api/sensors/<sensor_id>/sync
  получить desired_state

  если desired_state.config_version != локальная applied_version:
      сгенерировать docker-compose.yml
      сгенерировать cowrie/glutton/honeypy/conpot/mailoney configs
      остановить старые контейнеры EDC
      запустить нужные контейнеры
      сохранить applied_version
      отправить результат применения

  собрать состояние контейнеров
  прочитать логи контейнеров
  отправить события в центр
```

Код агента:

```text
sensor/agent.py
sensor/runtime.py
sensor/runtime_configs.py
sensor/runtime_status.py
sensor/runtime_helpers.py
```

Локальная структура на сенсоре формируется в каталоге состояния агента. В типовой установке это:

```text
/var/lib/edc-sensor/
└── docker-runtime/
    ├── docker-compose.yml
    ├── cowrie/
    ├── glutton/
    ├── honeypy/
    ├── conpot/
    └── mailoney/
```

Целевая структура для следующего этапа:

```text
/opt/honeysensor/
├── agent/
├── config/
│   ├── current/
│   └── versions/
├── logs/
│   ├── buffer/
│   └── agent.log
└── state/
    ├── sensor.json
    ├── runtime.json
    └── applied_version
```

## 9. Dockerfiles сенсора

Dockerfiles сенсора отделены от runtime-кода и лежат здесь:

```text
sensor/dockerfiles/
├── cowrie/Dockerfile
├── glutton/Dockerfile
├── glutton/config.yaml
├── glutton/rules.yaml
├── honeypy/Dockerfile
├── honeypy/etc/
├── conpot/Dockerfile
├── conpot/conpot.cfg
├── mailoney/Dockerfile
└── mailoney/mailoney_lite.py
```

Runtime копирует build context из `sensor/dockerfiles/<module>/` в рабочий каталог сенсора и использует его при `docker compose up --build`.

Сборка всех ARMv7-образов в bundle:

```bash
./scripts/prebuild_armv7_bundle.sh
```

Скрипт собирает:

```text
edc/cowrie:local
edc/conpot:local
edc/mailoney:local
edc/honeypy:local
edc/glutton:local
```

Результат сохраняется в:

```text
artifacts/edc-armv7-images-<date>.tar.gz
```

Ручная сборка одного образа:

```bash
docker buildx build \
  --platform linux/arm/v7 \
  --load \
  -t edc/glutton:local \
  -f sensor/dockerfiles/glutton/Dockerfile \
  sensor/dockerfiles/glutton
```

Загрузка bundle на сенсор:

```bash
scp artifacts/edc-armv7-images-*.tar.gz banana@192.168.0.239:/tmp/
ssh banana@192.168.0.239 'gzip -dc /tmp/edc-armv7-images-*.tar.gz | docker load'
```

## 10. Запуск центра

Первый запуск:

```bash
cp config/site.example.json config/site.local.json
make up
curl http://127.0.0.1:8080/health
```

Остановка:

```bash
make down
```

Просмотр контейнеров:

```bash
docker compose ps
docker compose logs -f manager-api
```

По умолчанию `compose.yml` поднимает PostgreSQL, Grafana и микросервисы control plane:

- `reverse-proxy` как публичный вход на порту `8080`;
- `manager-api` как внутренний UI/API на порту `8080`;
- `agent-gateway` на порту `8081`;
- `log-receiver` на порту `8091`;
- `config-renderer` на порту `8092`;
- `log-normalizer` без внешнего порта.

Если переменная `CENTER_DB_DSN` задана и начинается с `postgres`, сервисы пишут события в PostgreSQL. Если DSN не задан, используется SQLite в `var/center/events.sqlite3`.

Grafana доступна на порту `3000`. Учетные данные задаются переменными:

```text
GF_SECURITY_ADMIN_USER
GF_SECURITY_ADMIN_PASSWORD
```

В compose по умолчанию используется тестовая пара `centre` / `centre123`. Пароль `1` для Grafana не подходит, потому что Grafana проверяет минимальную сложность пароля. Для реального стенда пароль нужно заменить через compose override или переменные окружения.

В Grafana автоматически добавляются:

- datasource `EDC PostgreSQL`;
- dashboard `EDC Overview`;
- dashboard `EDC Honeypot Logs`;
- панели по событиям, сенсорам, профилям, honeypot-модулям, raw logs и нормализованным событиям.

Во встроенном UI центра в верхней панели есть кнопка `Grafana`. Она ведет сразу на dashboard `EDC Honeypot Logs`. URL берется из `GRAFANA_URL`, `site.grafana_url` или `site.observability.grafana_url`; если они не заданы, центр выводит `http://127.0.0.1:3000`.

## 11. Проверки проекта

Основная проверка:

```bash
make check
```

Она выполняет:

- компиляцию Python-модулей;
- проверку `catalog/device_mask_profiles.json`;
- проверку `config/site.example.json` против `catalog/honeypots.json`;
- проверку `docker compose config`.

Сквозная проверка API и генерации Docker Compose:

```bash
python3 tools/e2e_reconfigure_test.py
```

Проверка только профилей:

```bash
python3 tools/validate_profiles.py
```

Проверка только политики:

```bash
python3 tools/validate_policy.py
```

## 12. Что тестировать после сборки образов

После сборки и загрузки образов на Banana Pi Pro нужно проверить:

1. Центр:

```bash
docker compose ps
curl http://192.168.0.196:8080/health
curl http://192.168.0.196:8080/api/device-mask-profiles
```

2. Применение профиля:

```bash
curl -X POST http://192.168.0.196:8080/api/sensors/banana-pi-pro-1/apply-profile \
  -H 'Content-Type: application/json' \
  -d '{"profile_id":"ip-camera"}'
```

3. Сенсор:

```bash
ssh banana@192.168.0.239
systemctl status edc-sensor
journalctl -u edc-sensor -f
docker images | grep 'edc/'
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
ss -lntup
```

4. Проверка событий и нормализованных логов:

```bash
curl http://192.168.0.239:80/
nc -vz 192.168.0.239 554
nc -vz 192.168.0.239 23
curl http://192.168.0.196:8080/api/events?limit=20
curl http://192.168.0.196:8080/api/honeypot-events?limit=20
curl http://192.168.0.196:8080/api/logs/raw?limit=20
```

Если тест упал, полезные выводы для анализа:

```bash
docker compose ps
docker compose logs --tail=200 manager-api
docker compose logs --tail=200 reverse-proxy
curl http://192.168.0.196:8080/health
curl http://192.168.0.196:8080/api/sensors
systemctl status edc-sensor
journalctl -u edc-sensor --no-pager -n 200
docker ps -a
docker logs <container> --tail=200
ss -lntup
```

## 13. Текущая структура проекта

```text
.
├── catalog/
│   ├── honeypots.json
│   └── device_mask_profiles.json
├── center/
│   ├── api/handler.py
│   ├── core/
│   │   ├── auth.py
│   │   ├── log_normalizer.py
│   │   ├── overview.py
│   │   ├── paths.py
│   │   ├── policy.py
│   │   ├── profiles.py
│   │   └── sensor_sync.py
│   ├── persistence/
│   │   ├── events.py
│   │   ├── honeypot_logs.py
│   │   ├── sensor_states.py
│   │   └── store.py
│   ├── web/
│   │   ├── templates/admin.html
│   │   ├── templates/profiles.html
│   │   ├── templates/mask.html
│   │   └── views.py
│   ├── app.py
│   ├── main.py
│   └── Dockerfile
├── config/
│   └── site.example.json
├── sensor/
│   ├── dockerfiles/
│   ├── agent.py
│   ├── agent_state.py
│   ├── runtime.py
│   ├── runtime_configs.py
│   ├── runtime_helpers.py
│   └── runtime_status.py
├── scripts/
│   ├── check.sh
│   ├── prebuild_armv7_bundle.sh
│   ├── run_mvp.sh
│   └── run_sensor_runtime.sh
├── tools/
│   ├── e2e_reconfigure_test.py
│   ├── validate_policy.py
│   └── validate_profiles.py
├── observability/
│   └── grafana/
│       ├── dashboards/
│       └── provisioning/
├── services/
│   ├── reverse-proxy/
│   ├── agent-gateway/
│   ├── config-renderer/
│   ├── log-normalizer/
│   ├── log-receiver/
│   └── manager-api/
├── ansible/
│   ├── inventory.example.yml
│   └── playbooks/
├── compose.yml
├── Makefile
├── pyproject.toml
└── README.md
```

## 14. PostgreSQL и SQLite

В центре есть два режима хранения:

| Режим | Когда используется |
|---|---|
| PostgreSQL | `CENTER_DB_DSN` начинается с `postgres` |
| SQLite | `CENTER_DB_DSN` пустой или не postgres |

`compose.yml` сейчас поднимает PostgreSQL и передает `CENTER_DB_DSN` в центр. Для простого локального запуска без Postgres можно убрать эту переменную и зависимость из compose, тогда центр перейдет на SQLite.

Таблица `events` хранит совместимый журнал расследования: подключения к honeypot, ошибки runtime и проблемные статусы. Хороший регулярный `sensor.status` не пишется в `events`, чтобы не раздувать журнал.

Таблица `sensor_states` хранит последний технический статус каждого сенсора:

```text
sensor_id
updated_at
status
active_profile
config_version
applied_version
agent_mode
host
architecture
modules
active_services
listener_errors
raw_status
```

Логика такая:

- каждый heartbeat обновляет `sensor_states`;
- если статус здоровый, строка в `events` не создается;
- если статус содержит ошибки контейнеров, listener errors, `failed`, `degraded` или `skipped`, он сохраняется в `events` как диагностическое событие;
- события honeypot всегда пишутся в `events`.

Для крутых dashboard по настоящим honeypot-логам добавлены две специализированные таблицы.

`raw_honeypot_logs` хранит исходные строки логов:

```text
id
received_at
sensor_id
profile
device_type
honeypot
service
source_name
source_path
container_name
raw_line
parsed_json
raw_event
normalized_event_id
```

`honeypot_events` хранит нормализованные события:

```text
id
raw_log_id
received_at
timestamp
sensor_id
profile
device_type
honeypot
service
event_type
severity
src_ip
src_port
dst_ip
dst_port
username
password
command
url
http_method
user_agent
payload_sample
parser_name
parser_version
raw_event
```

Поток данных:

```text
sensor-agent
→ docker-runtime читает cowrie/glutton/honeypy/mailoney/conpot logs
→ /api/events или /logs/batch
→ raw_honeypot_logs
→ log_normalizer
→ honeypot_events
→ Grafana dashboard EDC Honeypot Logs
```

Нормализатор понимает типовые поля:

- Cowrie: `eventid`, `username`, `password`, `input`, `src_ip`;
- Mailoney: `eventid`, `verb`, `command`, `username`, `password`, `mail_from`, `rcpt_to`;
- Glutton: `dest_port`, `payload`, generic TCP/UDP interaction;
- HoneyPy: web/telnet/echo/random plugin logs;
- Conpot: industrial protocol interaction fields, если они появляются в JSON/log stream.

Запросы API:

```bash
curl http://127.0.0.1:8080/api/honeypot-events?limit=50
curl http://127.0.0.1:8080/api/logs/raw?limit=50
curl -X POST http://127.0.0.1:8091/logs/batch \
  -H 'Content-Type: application/json' \
  -d '{"events":[{"sensor_id":"test","module":"glutton","raw_sample":"dest_port=9100 payload=\"hello printer\""}]}'
```

Код хранения:

```text
center/persistence/store.py
center/persistence/events.py
center/persistence/sensor_states.py
center/persistence/honeypot_logs.py
center/core/log_normalizer.py
```

## 15. Ansible

Ansible в проекте используется как способ установки центра и сенсоров на реальные узлы. Это не обязательный путь для локальной разработки.

Файлы:

```text
ansible/inventory.example.yml
ansible/playbooks/site.yml
ansible/playbooks/center.yml
ansible/playbooks/sensors.yml
ansible/playbooks/classify_sensors.yml
ansible/playbooks/remove_sensor.yml
```

В текущей лабораторной схеме Ansible умеет:

- синхронизировать локальную рабочую копию проекта на центр и сенсор через `rsync`;
- создать compose override для авторизации центра;
- поднять `reverse-proxy`, `manager-api`, `agent-gateway`, `log-receiver`, `log-normalizer`, `config-renderer`, `postgres`, `grafana`;
- установить systemd-сервис `edc-sensor`;
- включить Docker;
- проверить активность сервиса сенсора;
- показать EDC-контейнеры, запущенные для выбранного `sensor_id`;
- на Banana Pi переименовать уже собранные `edc/*:banana` в runtime-имена `edc/*:local`.

Для запуска через временный inventory:

```bash
uvx --from ansible-core ansible-playbook \
  -i /tmp/edc-inventory.yml \
  ansible/playbooks/site.yml
```

В inventory для реального стенда нужно задать:

```yaml
edc_deploy_method: local_rsync
edc_center_auth_user: centre
edc_center_auth_password: "<пароль>"
edc_grafana_admin_user: centre
edc_grafana_admin_password: "<пароль не короче политики Grafana>"
edc_grafana_url: "http://192.168.0.196:3000"
edc_image_policy: prebuilt_only
edc_log_receiver_url: "http://192.168.0.196:8091/logs/batch"
```

Если `edc_log_receiver_url` пустой, агент отправляет события в старый совместимый endpoint `/api/events`. Если указан `log-receiver`, сырые логи идут сразу в микросервис приема логов.

Для Banana Pi рекомендуется `edc_image_policy: prebuilt_only`: агент не будет собирать контейнеры на слабом устройстве, а сообщит ошибку `missing prebuilt image`, если образ не загружен заранее.

Для разработки можно не запускать Ansible. Для ручного теста достаточно:

- поднять центр через Docker Compose;
- собрать и загрузить sensor Docker images;
- запустить agent/runtime на сенсоре;
- применить профиль через `/profiles` или API.

## 16. Микросервисная структура

Проект теперь разложен по сервисным директориям. Каждый сервис имеет отдельный Dockerfile:

| Сервис | Путь | Порт | Назначение |
|---|---|---:|---|
| reverse-proxy | `services/reverse-proxy` | 8080 | Публичный вход для UI/API и маршрутизация к сервисам |
| manager-api | `services/manager-api` | internal 8080 | UI, управление профилями, политика, совместимый API |
| agent-gateway | `services/agent-gateway` | 8081 | Узкий endpoint для агентов сенсоров |
| config-renderer | `services/config-renderer` | 8092 | Превращение `DeviceMaskProfile` в desired state |
| log-receiver | `services/log-receiver` | 8091 | Прием raw logs и batch events от сенсоров |
| log-normalizer | `services/log-normalizer` | - | Фоновая нормализация raw logs в `honeypot_events` |

В текущем compose наружу на `:8080` смотрит `reverse-proxy`, а рабочий Python-код центра работает как `manager-api`. Это оставляет старый URL центра стабильным для браузера и сенсоров, но внутри проект уже разложен на сервисы.

Проверка сервисов:

```bash
curl http://127.0.0.1:8080/health
curl http://127.0.0.1:8081/health
curl http://127.0.0.1:8091/health
curl http://127.0.0.1:8092/health
```

Рендер профиля без изменения политики:

```bash
curl -X POST http://127.0.0.1:8092/render \
  -H 'Content-Type: application/json' \
  -d '{"sensor_id":"preview-1","profile_id":"ip-camera"}'
```

## 17. Целевая архитектура следующего этапа

Текущая реализация остается компактной: один контейнер центра плюс PostgreSQL. Целевая промышленная схема может быть разнесена на отдельные сервисы:

```text
central-node
├── reverse-proxy
├── manager-ui
├── manager-api
├── agent-gateway
├── config-renderer
├── log-receiver
├── log-normalizer
├── postgres
├── redis
├── loki
└── grafana
```

Сенсор в целевой схеме:

```text
banana-pi-sensor
├── sensor-agent
├── cowrie
├── glutton
├── honeypy
├── conpot
└── mailoney
```

Сейчас эти роли уже вынесены в отдельные Dockerfile и сервисные директории. Следующий шаг - отдельный manager-ui, Redis для команд агента и Loki для длительного хранения сырых логов.

## 18. Команды, которые центр должен поддерживать дальше

План команд для следующего этапа:

```text
APPLY_PROFILE
START_PROFILE
STOP_PROFILE
RESTART_PROFILE
START_HONEYPOT
STOP_HONEYPOT
RESTART_HONEYPOT
UPDATE_CONFIG
ROLLBACK_CONFIG
COLLECT_STATUS
COLLECT_LOGS
```

Сейчас ключевая операция уже реализована через:

```text
POST /api/sensors/<id>/apply-profile
```

Очередь команд агента и история версий конфигурации должны быть следующей крупной задачей.

## 19. Что было убрано при чистке

Из проекта удалены разрозненные старые markdown-файлы, чтобы не было нескольких конкурирующих инструкций. Документация теперь ведется в `docs/system_guide_ru.md`.

Удаленные категории:

- старые `docs/architecture.md`, `docs/network.md`, `docs/roadmap.md` и похожие файлы;
- README в отдельных подпапках, которые дублировали главную документацию;
- временные файлы `1.txt`;
- старые backup-конфиги;
- локальные build artifacts.

Не удалять:

```text
ВКРТекст.md
config/site.local.json
var/
artifacts/, если там лежат свежие собранные образы
```

`artifacts/` не коммитится, потому что это тяжелые локальные результаты сборки.

## 20. Критерии готовности текущего этапа

Этап считается рабочим, если:

- `make check` проходит;
- `python3 tools/e2e_reconfigure_test.py` проходит;
- `/api/device-mask-profiles` возвращает 10 профилей;
- `/profiles` открывается в браузере;
- профиль применяется к сенсору через UI или API;
- агент получает `desired_state.active_profile`;
- Docker-runtime генерирует `docker-compose.yml`;
- контейнеры `cowrie`, `glutton`, `honeypy`, `conpot`, `mailoney` запускаются на сенсоре, когда нужны выбранному профилю;
- тестовое подключение к открытому порту появляется в `/api/events`;
- raw строка появляется в `/api/logs/raw`;
- нормализованная запись появляется в `/api/honeypot-events`;
- dashboard `EDC Honeypot Logs` отображает события по honeypot, профилю, source IP и порту.
