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

Страница `http://<central-ip>:8080/settings` используется для управления центром и сенсорами. При добавлении сенсора центр не делает вид, что узел уже установлен: он создает запись в политике и показывает статус обработки `waiting_agent`. После первого `sync` от `sensor-agent` статус меняется на `completed`, `stale` или `error` в зависимости от heartbeat и ошибок runtime.

В этом же разделе есть режим `Установить по SSH`. Он нужен для чистого узла, на который администратор не хочет заходить вручную. Центр принимает `sensor_id`, адрес узла, SSH-пользователя, пароль sudo, профиль и рабочий каталог, после чего выполняет bootstrap:

1. Проверяет SSH-доступ.
2. Ставит Docker, compose plugin и Python через `apt`, `pacman` или `dnf`.
3. Копирует на сенсор минимальный bundle: `compose.sensor.yml` и каталог `sensor/`.
4. Создает `.env` с `EDC_CENTER_URL`, `EDC_SENSOR_ID`, `EDC_IMAGE_POLICY`.
5. Запускает `docker compose -f compose.sensor.yml up -d --build`.
6. Отображает ход установки в `/settings` как install job.

Такой поток не требует ручной работы на сенсоре. Минимальное требование к чистому железу - включенный SSH, пользователь с sudo и сетевой доступ до центра. Для слабых ARMv7-плат рекомендуется готовить образ ОС заранее: Docker уже установлен, а honeypot-образы `edc/cowrie:local`, `edc/glutton:local`, `edc/honeypy:local`, `edc/mailoney:local`, `edc/conpot:local` загружены через `docker load`. В этом случае используется `EDC_IMAGE_POLICY=prebuilt_only`, и Banana Pi не тратит время на сборку тяжелых контейнеров.

Для контейнерного запуска агента на сенсоре используется отдельный compose-файл:

```bash
export EDC_CENTER_URL=http://<central-ip>:8080
export EDC_SENSOR_ID=banana-pi-pro-1
export EDC_IMAGE_POLICY=prebuilt_only
docker compose -f compose.sensor.yml up -d --build
```

Контейнер `sensor-agent` монтирует `/var/run/docker.sock` и `/var/lib/edc-sensor`. Поэтому сам агент работает в контейнере, но управляет honeypot-контейнерами хостового Docker и сохраняет `docker-compose.yml`, конфиги и логи на хосте сенсора.

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

## 21. Быстрый старт для нового разработчика

Этот раздел нужен человеку, который впервые открыл проект и хочет понять, что запускать.

Минимальный локальный запуск центра:

```bash
cp config/site.example.json config/site.local.json
make up
curl -u centre:1 http://127.0.0.1:8080/health
```

Открыть в браузере:

```text
http://127.0.0.1:8080/settings
```

Учетные данные центра по умолчанию:

```text
login:    centre
password: 1
```

Grafana:

```text
http://127.0.0.1:3000
login:    centre
password: centre123
```

Если Grafana не принимает `centre / centre123`, значит volume `grafana_data` был создан раньше с другим паролем. Сбросить пароль можно так:

```bash
docker exec edc-grafana grafana cli admin reset-admin-password centre123
```

Если также нужно переименовать стандартного пользователя `admin` в `centre`:

```bash
curl -u admin:admin \
  -H 'Content-Type: application/json' \
  -X PUT http://127.0.0.1:3000/api/users/1 \
  -d '{"name":"EDC Grafana Admin","email":"centre@edc.local","login":"centre","theme":"light"}'
```

Проверить, что логин работает:

```bash
curl -u centre:centre123 http://127.0.0.1:3000/api/user
```

Минимальная проверка проекта после изменения кода:

```bash
make check
make e2e
docker compose ps
```

## 22. Лабораторные переменные стенда

Не нужно зашивать IP-адреса в команды и код. Для стенда удобно держать локальный файл `.edc-lab.env`, который не коммитится:

```bash
cat > .edc-lab.env <<'EOF'
export CENTER_IP=192.168.0.121
export SENSOR_IP=192.168.0.239
export SENSOR_USER=banana
export SENSOR_ID=banana-pi-pro-1
export CENTER_URL="http://${CENTER_IP}:8080"
export GRAFANA_URL="http://${CENTER_IP}:3000"
EOF

source .edc-lab.env
```

После этого команды становятся переносимыми:

```bash
curl -u centre:1 "$CENTER_URL/health"
ssh "$SENSOR_USER@$SENSOR_IP" 'docker ps'
```

Если в другой сети центр получил новый адрес, меняется только `.edc-lab.env` и поле `site.central_url` в UI `/settings`.

Внутренние Docker-адреса `172.x.x.x` фиксировать не нужно. Они меняются между запусками и не являются частью контракта проекта.

## 23. Установка центра на чистую машину

Требования к узлу центра:

- Linux x86_64 или aarch64;
- Docker Engine;
- Docker Compose plugin;
- Git;
- свободные порты `8080`, `8081`, `8091`, `8092`, `3000`, `5432`, если используется полный compose.

Установка:

```bash
git clone https://github.com/SoffTiAmS2/early-detection-complex.git
cd early-detection-complex
cp config/site.example.json config/site.local.json
docker compose up -d --build
```

Проверка:

```bash
docker compose ps
curl -u centre:1 http://127.0.0.1:8080/health
curl -u centre:1 http://127.0.0.1:8080/api/device-mask-profiles
```

Если центр запускается в локальной сети, открой `/settings` и выставь:

```text
Center URL: http://<ip-центра>:8080
Mgmt network: <подсеть управления>
```

Эти значения сохраняются в рабочую политику и нужны для bootstrap сенсоров.

## 24. Установка сенсора без ручного входа на сенсор

Основной путь установки сенсора сейчас - через UI центра:

```text
http://<central-ip>:8080/settings
```

Блок:

```text
Создать и установить сенсор
```

Поля:

| Поле | Назначение |
|---|---|
| `ID` | стабильный идентификатор сенсора, например `banana-pi-pro-1` |
| `Host` | IP или DNS-имя сенсора |
| `SSH user` | пользователь на сенсоре |
| `SSH password / sudo` | пароль SSH и sudo |
| `SSH port` | обычно `22` |
| `Profile` | профиль маскировки устройства |
| `Remote dir` | каталог установки проекта на сенсоре |
| `Clone from` | сенсор-образец для первичной политики |
| `Image policy` | `prebuilt_only` или `build_if_missing` |

Кнопка `Только создать` добавляет сенсор в политику и переводит его в состояние ожидания агента.

Кнопка `Установить по SSH` делает полный bootstrap:

1. Создает или обновляет запись сенсора в политике.
2. Применяет выбранный `DeviceMaskProfile`.
3. Проверяет SSH-доступ.
4. Устанавливает Docker, compose plugin и Python через пакетный менеджер.
5. Если Docker не найден после установки пакетов, использует fallback `get.docker.com`.
6. Загружает найденные локальные ARMv7 image artifacts из `artifacts/`.
7. Копирует `compose.sensor.yml` и каталог `sensor/`.
8. Создает `.env` с `EDC_CENTER_URL`, `EDC_SENSOR_ID`, `EDC_IMAGE_POLICY`.
9. Запускает `docker compose --env-file .env -f compose.sensor.yml up -d --build`.
10. Показывает прогресс и лог установки на странице `/settings`.

Bootstrap job сейчас хранится в памяти процесса `manager-api`. После перезапуска `manager-api` история активных bootstrap jobs будет потеряна, но созданный сенсор и политика сохранятся. Следующий этап - перенести bootstrap jobs в таблицу БД.

## 25. Что должно быть в золотом образе сенсора

Для слабых ARMv7-устройств, например Banana Pi Pro, не стоит собирать тяжелые honeypot-образы прямо на устройстве. Лучше подготовить образ ОС заранее.

В золотом образе желательно иметь:

- включенный SSH;
- пользователь с sudo;
- Docker Engine;
- Docker Compose plugin;
- Python 3;
- `curl`, `ca-certificates`, `gzip`, `tar`;
- загруженные Docker images:
  - `edc/cowrie:local`;
  - `edc/glutton:local`;
  - `edc/honeypy:local`;
  - `edc/mailoney:local`;
  - `edc/conpot:local`.

Проверка на сенсоре:

```bash
docker compose version
docker image ls | grep '^edc/'
```

Для такого сенсора выбирай:

```text
Image policy: prebuilt_only
```

Если образ отсутствует, агент не будет компилировать его на плате, а покажет ошибку вида:

```text
missing prebuilt image: edc/honeypy:local
```

Это правильное поведение: оно защищает слабое устройство от долгой сборки и зависаний.

## 26. Сборка и перенос honeypot-образов

Сборка полного ARMv7 bundle:

```bash
./scripts/prebuild_armv7_bundle.sh
```

Если нужен один образ:

```bash
docker buildx build \
  --platform linux/arm/v7 \
  --load \
  -t edc/honeypy:local \
  -f sensor/dockerfiles/honeypy/Dockerfile \
  sensor/dockerfiles/honeypy
```

Сохранить образ:

```bash
mkdir -p artifacts/docker-images
docker save edc/honeypy:local | gzip -1 > artifacts/docker-images/edc_honeypy_local_armv7.tar.gz
sha256sum artifacts/docker-images/edc_honeypy_local_armv7.tar.gz \
  > artifacts/docker-images/edc_honeypy_local_armv7.tar.gz.sha256
```

Загрузить на сенсор:

```bash
scp artifacts/docker-images/edc_honeypy_local_armv7.tar.gz banana@192.168.0.239:/tmp/
ssh banana@192.168.0.239 \
  'gzip -dc /tmp/edc_honeypy_local_armv7.tar.gz | sudo docker load'
```

Автоматический SSH bootstrap центра также пытается найти подходящие архивы в `artifacts/`, потому что `manager-api` монтирует:

```text
./artifacts:/app/artifacts:ro
```

Архивы с именами, содержащими `edc`, `armv7`, `banana` или `local`, будут кандидатами на загрузку.

## 27. Контракт контейнеров сенсора

Этот раздел фиксирует, что должен уметь каждый honeypot image, чтобы runtime мог запускать его без ручной отладки.

### 27.1 Cowrie

Назначение:

```text
SSH/Telnet honeypot
```

Image:

```text
edc/cowrie:local
```

Порты внутри контейнера:

| Сервис | Container port |
|---|---:|
| SSH | `2222/tcp` |
| Telnet | `2223/tcp` |

Runtime mounts:

```text
cowrie/config/cowrie.cfg  -> /home/cowrie/cowrie/etc/cowrie.cfg:ro
cowrie/config/userdb.txt  -> /home/cowrie/cowrie/etc/userdb.txt:ro
cowrie/logs/              -> /home/cowrie/cowrie/var/log/cowrie
cowrie/downloads/         -> /home/cowrie/cowrie/var/lib/cowrie/downloads
cowrie/tty/               -> /home/cowrie/cowrie/var/lib/cowrie/tty
```

Основные логи:

```text
cowrie/logs/cowrie.json
cowrie/logs/cowrie.log
cowrie/tty/*
```

Что должен парсить центр:

- `cowrie.session.connect`;
- `cowrie.login.success`;
- `cowrie.login.failed`;
- `cowrie.command.input`;
- `cowrie.session.closed`;
- `src_ip`;
- `username`;
- `password`;
- `input` как команда.

Проверка:

```bash
nc -vz <sensor-ip> 23
telnet <sensor-ip> 23
```

### 27.2 Glutton

Назначение:

```text
универсальный TCP/UDP honeypot для портов, где не нужен глубокий протокол
```

Image:

```text
edc/glutton:local
```

Команда:

```text
glutton --confpath /etc/glutton --ssh 22 --var-dir /var/lib/glutton --logpath /logs/glutton.log
```

Runtime mounts:

```text
glutton/config/ -> /etc/glutton:ro
glutton/logs/   -> /logs
glutton/data/   -> /var/lib/glutton
```

Capabilities:

```text
NET_ADMIN
NET_RAW
```

Основные логи:

```text
glutton/logs/glutton.log
```

Что должен парсить центр:

- `dest_port`;
- `src_ip`;
- `payload`;
- HTTP method/path из payload;
- generic connection для нестандартных TCP payload;
- UDP/SNMP-подключения, если Glutton их пишет.

Проверка:

```bash
printf 'hello printer\r\n' | nc <sensor-ip> 9100
printf 'GET / HTTP/1.1\r\nHost: x\r\n\r\n' | nc <sensor-ip> 8000
```

### 27.3 HoneyPy

Назначение:

```text
легкие web panels, Telnet-like, Elasticsearch-like, Echo/MOTD/Random
```

Image:

```text
edc/honeypy:local
```

Порты внутри контейнера:

| Сервис | Container port |
|---|---:|
| Web | `10080/tcp` |
| Telnet | `10023/tcp` |
| Elasticsearch | `19200/tcp` |
| Echo | `10007/tcp` |
| MOTD | `10008/tcp` |
| Random | `12048/tcp` |

Runtime mounts:

```text
honeypy/config/    -> /config:ro
honeypy/image/etc/ -> /opt/HoneyPy/etc:ro
honeypy/logs/      -> /opt/HoneyPy/logs
honeypy/logs/      -> /logs
```

Основные логи:

```text
honeypy/logs/honeypy-events.json
honeypy/logs/internal/honeypy.log
```

Что должен парсить центр:

- HTTP request method/path;
- Telnet interaction;
- Elasticsearch probe;
- source IP;
- payload_sample.

Проверка:

```bash
curl -i http://<sensor-ip>:80/
nc -vz <sensor-ip> 9200
```

Важно: SMTP в HoneyPy не используется как основной SMTP honeypot. Для SMTP используется Mailoney.

### 27.4 Mailoney

Назначение:

```text
SMTP honeypot
```

Image:

```text
edc/mailoney:local
```

Порт внутри контейнера:

```text
2525/tcp
```

Runtime mounts:

```text
mailoney/config/mailoney.cfg -> /etc/mailoney/mailoney.cfg:ro
mailoney/logs/               -> /logs
```

Основные переменные:

```text
MAILONEY_SERVER_NAME
MAILONEY_LOG_DIR=/logs
MAILONEY_LOGIN_RESULT
EDC_SENSOR_ID
```

Основные логи:

```text
mailoney/logs/mailoney.jsonl
mailoney/logs/messages/*.eml
```

Что должен парсить центр:

- SMTP `EHLO` / `HELO`;
- `AUTH LOGIN`;
- `AUTH PLAIN`;
- `MAIL FROM`;
- `RCPT TO`;
- `DATA`;
- username/password при попытке аутентификации;
- sender/recipient.

Проверка:

```bash
nc <sensor-ip> 25
EHLO test.local
QUIT
```

### 27.5 Conpot

Назначение:

```text
ICS/SCADA honeypot
```

Image:

```text
edc/conpot:local
```

Порты внутри контейнера:

| Сервис | Container port |
|---|---:|
| Modbus | `5020/tcp` |
| S7Comm | `10201/tcp` |
| HTTP | `8800/tcp` |
| EtherNet/IP-like | `44818/tcp` |

Runtime mounts:

```text
conpot/config/conpot.cfg -> /etc/conpot/conpot.cfg:ro
conpot/logs/             -> /logs
conpot/data/             -> /data
conpot/tmp/              -> /tmp/conpot
```

Команда:

```text
conpot --template default \
  --config /etc/conpot/conpot.cfg \
  --logfile /logs/conpot.log \
  --temp_dir /tmp/conpot
```

Основные логи:

```text
conpot/logs/conpot.log
conpot/logs/conpot.json
```

Что должен парсить центр:

- протокол;
- session / request;
- source IP;
- destination port;
- Modbus/S7-like interaction;
- HTTP path, если запрос шел в web panel.

Проверка:

```bash
nc -vz <sensor-ip> 502
curl -i http://<sensor-ip>:80/
```

Важное правило: если в образе нет template `industrial-controller`, runtime должен использовать `--template default`. Профиль `industrial-controller` - это EDC-легенда, а не обязательно имя каталога template внутри Conpot.

## 28. Состояния сенсора и почему счетчики могут быть 0

На `/settings` есть несколько разных чисел, и они означают разные вещи.

| Показатель | Что означает |
|---|---|
| `Всего сенсоров` | количество сенсоров в политике |
| `Online` | сенсоры с недавним heartbeat |
| `Ожидают / stale` | сенсоры без первого sync или с устаревшим heartbeat |
| `Активные сервисы` | количество реально запущенных сервисов в runtime status |
| `Модулей в политике` | включенные honeypot-модули в desired state |
| `События` | события безопасности, не технические healthy heartbeat |

Хороший регулярный статус не загрязняет таблицу `events`. Поэтому счетчик `События` может быть `0`, даже если сенсор работает. Это нормально.

Сенсор считается:

| Состояние | Причина |
|---|---|
| `waiting_agent` | сенсор есть в политике, но агент еще ни разу не прислал sync |
| `online` | есть свежий heartbeat и нет ошибок runtime |
| `degraded` | агент жив, часть сервисов запущена, но есть ошибки, например missing image |
| `stale` | сенсор был online, но heartbeat устарел |
| `error` | runtime не поднял ни одного honeypot или сообщил критичные ошибки |
| `never_seen` | от сенсора не было ни одного статуса |

Пример частично рабочего Banana Pi:

```text
banana-pi-pro-1
status: online/degraded
active_services: 4
error: missing prebuilt image: edc/honeypy:local
```

Это значит: агент установлен, Cowrie/Glutton работают, но профиль не полностью применен, потому что нет image HoneyPy.

## 29. Диагностика центра

Быстрая проверка:

```bash
docker compose ps
curl -u centre:1 http://127.0.0.1:8080/health
curl -u centre:1 http://127.0.0.1:8080/api/sensors
curl -u centre:1 http://127.0.0.1:8080/api/db/stats
```

Логи:

```bash
docker compose logs --tail=200 manager-api
docker compose logs --tail=200 reverse-proxy
docker compose logs --tail=200 log-receiver
docker compose logs --tail=200 log-normalizer
docker compose logs --tail=200 grafana
```

Проверка PostgreSQL:

```bash
docker exec -it edc-postgres psql -U edc -d edc -c '\dt'
docker exec -it edc-postgres psql -U edc -d edc -c 'select count(*) from events;'
docker exec -it edc-postgres psql -U edc -d edc -c 'select count(*) from honeypot_events;'
```

Проверка API логов:

```bash
curl -u centre:1 'http://127.0.0.1:8080/api/logs/raw?limit=10'
curl -u centre:1 'http://127.0.0.1:8080/api/honeypot-events?limit=10'
```

Если UI не открывается:

1. Проверить `docker compose ps`.
2. Проверить, что порт `8080` не занят другим процессом.
3. Проверить `docker compose logs reverse-proxy manager-api`.
4. Проверить Basic Auth.

## 30. Диагностика сенсора

На сенсоре:

```bash
docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
docker image ls | grep '^edc/'
sudo find /var/lib/edc-sensor/docker-runtime -maxdepth 3 -type f | sort
sudo ss -lntup
```

Логи контейнерного агента:

```bash
docker logs --tail=200 edc-sensor-agent-banana-pi-pro-1
```

Если еще остался старый systemd-агент:

```bash
systemctl status edc-sensor
journalctl -u edc-sensor --no-pager -n 200
```

Если одновременно работает старый systemd-агент и новый container-agent, это может путать диагностику. Для чистой контейнерной схемы старый сервис можно отключить:

```bash
sudo systemctl disable --now edc-sensor
```

Проверить сгенерированный compose:

```bash
sudo sed -n '1,240p' /var/lib/edc-sensor/docker-runtime/docker-compose.yml
```

Типовые ошибки:

| Ошибка | Причина | Действие |
|---|---|---|
| `missing prebuilt image` | образ не загружен на сенсор | загрузить `edc/<module>:local` через `docker load` |
| `port is already allocated` | порт занят старым контейнером или сервисом | остановить конфликтующий процесс |
| `docker executable not found` | Docker не установлен | установить Docker или запустить SSH bootstrap |
| `docker compose plugin ... unavailable` | нет compose plugin | установить `docker-compose-plugin` |
| `/logs Permission denied` | host directory не writable для user контейнера | исправить owner/permissions runtime каталога |
| `Template not found` у Conpot | неверный template name | использовать `default` или добавить template в образ |

## 31. Smoke-тесты honeypot-профилей

Перед демонстрацией нужно проверить не только UI, но и реальные порты.

IP-камера:

```bash
curl -i http://<sensor-ip>:80/
printf 'OPTIONS rtsp://x/ RTSP/1.0\r\n\r\n' | nc <sensor-ip> 554
printf 'admin\r\n123456\r\n' | nc <sensor-ip> 23
```

Принтер:

```bash
curl -i http://<sensor-ip>:80/
printf 'hello printer\r\n' | nc <sensor-ip> 9100
nc -vz <sensor-ip> 631
```

Роутер:

```bash
nc -vz <sensor-ip> 22
nc -vz <sensor-ip> 23
curl -i http://<sensor-ip>:80/
nc -vz <sensor-ip> 8291
```

Mail server:

```bash
nc <sensor-ip> 25
EHLO test.local
AUTH PLAIN dGVzdAB0ZXN0ADEyMzQ1Ng==
QUIT
```

Industrial controller:

```bash
nc -vz <sensor-ip> 502
nc -vz <sensor-ip> 102
curl -i http://<sensor-ip>:80/
nc -vz <sensor-ip> 44818
```

После smoke-теста проверить центр:

```bash
curl -u centre:1 'http://<center-ip>:8080/api/honeypot-events?limit=20'
curl -u centre:1 'http://<center-ip>:8080/api/logs/raw?limit=20'
```

## 32. Log pipeline и парсинг логов

Цель log pipeline - не просто хранить строки контейнеров, а получать нормальные поля для dashboard:

```text
sensor_id
profile
device_type
honeypot
service
event_type
severity
src_ip
src_port
dst_port
username
password
command
url
http_method
user_agent
payload_sample
```

Поток:

```text
sensor-agent
  -> читает файлы logs и docker logs
  -> отправляет raw event в центр
manager-api / log-receiver
  -> пишет raw_honeypot_logs
log-normalizer
  -> строит honeypot_events
Grafana
  -> читает PostgreSQL datasource
```

Нормализатор находится в:

```text
center/core/log_normalizer.py
```

Если добавляется новый формат логов, править нужно:

1. `normalize_honeypot_event()`;
2. `_event_type()`;
3. `_severity()`;
4. `_payload_sample()`;
5. при необходимости `_credential()`.

Проверка нормализатора:

```bash
python3 tools/check_log_normalizer.py
```

Перепарсить сохраненные raw logs:

```bash
python3 tools/reparse_honeypot_logs.py
```

Если лог содержит пароль, он сохраняется в `honeypot_events.password`. Это удобно для лаборатории, но для публичных отчетов такие поля нужно обезличивать.

## 33. Работа с Grafana

Grafana поднимается контейнером `edc-grafana`.

URL по умолчанию:

```text
http://<center-ip>:3000
```

Dashboards лежат в:

```text
observability/grafana/dashboards/
```

Provisioning:

```text
observability/grafana/provisioning/datasources/postgres.yml
observability/grafana/provisioning/dashboards/dashboards.yml
```

Основные dashboard:

| Dashboard | Назначение |
|---|---|
| `EDC Overview` | общий обзор сенсоров, профилей и событий |
| `EDC Honeypot Logs` | сырые и нормализованные honeypot-события |

Если Grafana открывается, но данных нет:

1. Проверить, что `edc-postgres` healthy.
2. Проверить datasource в Grafana.
3. Проверить таблицы `raw_honeypot_logs` и `honeypot_events`.
4. Проверить, что сенсор реально отправляет события.
5. Проверить `log-normalizer`.

Команды:

```bash
docker compose logs --tail=100 grafana
docker compose logs --tail=100 log-normalizer
docker exec edc-postgres psql -U edc -d edc -c 'select count(*) from honeypot_events;'
```

## 34. База данных и таблицы

Основные таблицы:

| Таблица | Назначение |
|---|---|
| `events` | совместимый журнал событий и ошибок runtime |
| `sensor_states` | последнее состояние каждого сенсора |
| `raw_honeypot_logs` | сырые строки и JSON-логи honeypot-контейнеров |
| `honeypot_events` | нормализованные события для UI/Grafana |
| `schema_migrations` | версия схемы SQLite/PostgreSQL |

Правило хранения:

- здоровые heartbeat не пишутся в `events`;
- проблемные status пишутся в `events`;
- honeypot-взаимодействия пишутся в `events`, `raw_honeypot_logs` и `honeypot_events`, если нормализатор смог выделить полезное событие;
- raw logs сохраняются даже тогда, когда нормализатор пропустил строку как служебную.

Проверить размеры таблиц:

```bash
docker exec edc-postgres psql -U edc -d edc -c "
select 'events' as table_name, count(*) from events
union all select 'sensor_states', count(*) from sensor_states
union all select 'raw_honeypot_logs', count(*) from raw_honeypot_logs
union all select 'honeypot_events', count(*) from honeypot_events;
"
```

Очистка через API:

```bash
curl -u centre:1 -X POST http://127.0.0.1:8080/api/db/purge
```

Перед очисткой реального стенда нужно сохранить backup.

## 35. Backup и восстановление

Что нужно сохранять:

```text
config/site.local.json
catalog/device_mask_profiles.json, если менялся вручную
var/center/, если используется SQLite
postgres_data volume, если используется PostgreSQL
grafana_data volume, если менялись пользователи или dashboard вручную
artifacts/docker-images/*.tar.gz
```

Backup PostgreSQL:

```bash
mkdir -p backups
docker exec edc-postgres pg_dump -U edc -d edc > backups/edc-$(date +%Y%m%d-%H%M%S).sql
```

Restore PostgreSQL:

```bash
cat backups/edc-YYYYMMDD-HHMMSS.sql | docker exec -i edc-postgres psql -U edc -d edc
```

Backup runtime-конфигов сенсора:

```bash
ssh banana@<sensor-ip> \
  'sudo tar -C /var/lib/edc-sensor -czf - docker-runtime' \
  > backups/sensor-runtime-$(date +%Y%m%d-%H%M%S).tar.gz
```

## 36. Безопасная эксплуатация

Сенсор считается недоверенным узлом. Honeypot-контейнеры принимают чужие подключения, поэтому их нельзя запускать с лишними правами.

Правила:

- не монтировать `/var/run/docker.sock` внутрь honeypot-контейнеров;
- `docker.sock` монтируется только в `sensor-agent`;
- не использовать `--privileged` без крайней необходимости;
- Glutton получает только `NET_ADMIN` и `NET_RAW`;
- Conpot, Cowrie, HoneyPy, Mailoney должны работать без дополнительных capabilities;
- не публиковать PostgreSQL и Grafana наружу без пароля и firewall;
- сырые логи считать чувствительными данными;
- не коммитить реальные raw logs, пароли, SSH-ключи, письма, IP-адреса внешних источников.

Рекомендуемая сеть:

```text
LAN/DMZ -> honeypot ports on sensor
sensor -> center:8080/8091
admin -> center:8080/3000
admin -> sensor:22
sensor -> LAN internal: deny by firewall, кроме центра
```

Для демонстрации в учебной лаборатории можно использовать одну подсеть, но в отчете нужно указать, что промышленная эксплуатация требует VLAN/DMZ и ограничения исходящих соединений сенсора.

## 37. Что нельзя коммитить

Не коммитить:

```text
artifacts/
var/
backups/
__pycache__/
*.pyc
.edc-lab.env
config/site.local.json
реальные raw логи honeypot
дампы PostgreSQL
личные SSH-ключи
ВКРТекст.md
```

Файл `ВКРТекст.md` не трогать при инженерных правках. Это текст выпускной работы, а не operational documentation.

Перед коммитом:

```bash
git status --short
make check
make e2e
```

## 38. Карта основных файлов

| Путь | Назначение |
|---|---|
| `README.md` | короткий вход в проект |
| `docs/system_guide_ru.md` | главная документация |
| `compose.yml` | полный центр: reverse-proxy, API, микросервисы, PostgreSQL, Grafana |
| `compose.sensor.yml` | контейнерный `sensor-agent` для сенсора |
| `catalog/device_mask_profiles.json` | профили маскировки устройств |
| `catalog/honeypots.json` | технический каталог honeypot-модулей |
| `config/site.example.json` | пример рабочей политики |
| `center/api/handler.py` | UI/API центра |
| `center/core/profiles.py` | преобразование профиля в desired state |
| `center/core/bootstrap.py` | SSH bootstrap сенсора |
| `center/core/log_normalizer.py` | нормализация логов honeypot |
| `center/core/overview.py` | сводка для UI |
| `center/persistence/store.py` | схема БД и подключение |
| `center/persistence/honeypot_logs.py` | raw logs и normalized events |
| `sensor/agent.py` | агент сенсора |
| `sensor/runtime.py` | Docker-runtime на сенсоре |
| `sensor/runtime_configs.py` | генерация конфигов honeypot |
| `sensor/runtime_status.py` | чтение состояния контейнеров |
| `sensor/dockerfiles/` | Dockerfiles реальных honeypot-образов |
| `services/reverse-proxy/` | Nginx вход в центр |
| `services/agent-gateway/` | отдельный endpoint для агентов |
| `services/log-receiver/` | прием raw logs |
| `services/log-normalizer/` | фоновый normalizer |
| `services/config-renderer/` | preview/render desired state |
| `observability/grafana/` | Grafana datasource и dashboards |
| `ansible/` | установка центра и сенсоров через Ansible |
| `scripts/prebuild_armv7_bundle.sh` | сборка ARMv7 image bundle |
| `scripts/check.sh` | локальные проверки проекта |
| `tools/e2e_reconfigure_test.py` | сквозной тест API/runtime generation |

## 39. Как добавлять новый DeviceMaskProfile

1. Открыть `catalog/device_mask_profiles.json`.
2. Добавить объект в `profiles`.
3. Заполнить:
   - `id`;
   - `name`;
   - `title`;
   - `device_type`;
   - `description`;
   - `legend`;
   - `exposed_ports`;
   - `honeypots`;
   - `banners`;
   - `service_fingerprints`;
   - `docker_template`;
   - `config_templates`;
   - `resource_limits`;
   - `logging`;
   - `detection_goals`.
4. Убедиться, что каждый `honeypot` существует в `catalog/honeypots.json`.
5. Убедиться, что каждый `module_service` существует в нужном модуле.
6. Запустить:

```bash
python3 tools/validate_profiles.py
make check
```

7. Проверить preview:

```bash
curl -X POST http://127.0.0.1:8092/render \
  -H 'Content-Type: application/json' \
  -d '{"sensor_id":"preview","profile_id":"new-profile-id"}'
```

8. Применить профиль на тестовый сенсор через `/profiles`.

## 40. Как добавлять новый honeypot-модуль

1. Добавить Dockerfile в:

```text
sensor/dockerfiles/<module>/
```

2. Добавить модуль в `catalog/honeypots.json`.
3. Добавить image name в `sensor/runtime_helpers.py`.
4. Добавить генерацию конфигов в `sensor/runtime_configs.py`.
5. Добавить compose volumes/environment/command при необходимости в `sensor/runtime.py`.
6. Добавить парсер логов в `center/core/log_normalizer.py`.
7. Добавить smoke-тест в документацию.
8. Запустить:

```bash
make check
make e2e
```

9. Собрать образ для нужной архитектуры и загрузить на сенсор.

## 41. Runbook для демонстрации

Перед демонстрацией:

```bash
source .edc-lab.env
docker compose ps
curl -u centre:1 "$CENTER_URL/health"
curl -u centre:1 "$CENTER_URL/api/sensors"
```

Открыть:

```text
http://<center-ip>:8080/settings
http://<center-ip>:8080/profiles
http://<center-ip>:3000
```

Проверить сенсор:

```bash
ssh "$SENSOR_USER@$SENSOR_IP" 'docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"'
ssh "$SENSOR_USER@$SENSOR_IP" 'sudo ss -lntup'
```

Сгенерировать события:

```bash
curl -i "http://$SENSOR_IP:80/"
printf 'GET /login.cgi HTTP/1.1\r\nHost: camera\r\n\r\n' | nc "$SENSOR_IP" 80
printf 'OPTIONS rtsp://camera/ RTSP/1.0\r\n\r\n' | nc "$SENSOR_IP" 554
printf 'root\r\nadmin\r\n' | nc "$SENSOR_IP" 23
```

Показать результат:

```bash
curl -u centre:1 "$CENTER_URL/api/honeypot-events?limit=20"
```

В UI:

1. `/settings` - сенсор online/degraded/completed, активные сервисы и ошибки.
2. `/profiles` - выбранный профиль устройства.
3. Grafana `EDC Honeypot Logs` - нормализованные события, source IP, ports, credentials, payload.

Если во время демонстрации сервис не поднимается:

```bash
ssh "$SENSOR_USER@$SENSOR_IP" 'docker logs --tail=120 edc-sensor-agent-banana-pi-pro-1'
ssh "$SENSOR_USER@$SENSOR_IP" 'docker ps -a'
curl -u centre:1 "$CENTER_URL/api/sensors"
```

## 42. Roadmap

Ближайшие инженерные задачи:

1. Перенести bootstrap jobs из памяти процесса в PostgreSQL/SQLite.
2. Добавить в UI кнопку retry для неудачной установки сенсора.
3. Добавить очистку старого systemd-agent при переходе на container-agent.
4. Довести `sensor_token` отдельно от admin auth.
5. Сделать очередь команд агента:
   - `START_PROFILE`;
   - `STOP_PROFILE`;
   - `RESTART_PROFILE`;
   - `ROLLBACK_CONFIG`;
   - `COLLECT_LOGS`.
6. Добавить историю версий конфигурации сенсора.
7. Добавить per-module resource limits вместо одного общего лимита профиля.
8. Добавить policy для срока хранения raw logs.
9. Добавить sanitization export для диплома и публичных отчетов.
10. Расширить Grafana dashboard по профилям:
    - top attacked profile;
    - top source IP;
    - credentials table;
    - protocol mix;
    - missing images/runtime errors.

До выполнения этих задач ядро проекта уже usable как лабораторный комплекс, но промышленным продуктом его считать рано.
