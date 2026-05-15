# Early Detection Complex: единая документация проекта

Этот файл является основной и единственной подробной документацией проекта.
Разрозненные документы из `docs/`, README внутри подпакетов и временные
заметки удалены, чтобы проект можно было понять с одного места.

`ВКРТекст.md` не относится к инженерной документации проекта и не редактируется
в рамках рефакторинга кода.

## 1. Назначение

Early Detection Complex, или EDC, - распределенный комплекс раннего выявления
подозрительной сетевой активности. Комплекс размещает управляемые сенсоры в
локальной сети, запускает на них honeypot-сервисы и отправляет события на
центральный узел.

Основная идея простая: если к ложному сервису подключились, значит в сегменте
есть активность, которую стоит проверить. Это может быть сканирование,
попытка входа, обращение к промышленному протоколу, проверка SMTP, попытка
найти Docker API или другой сетевой probe.

EDC не является SIEM, IPS, EDR или firewall. Он не блокирует атаку. Он создает
ранний сигнал, сохраняет контекст события и дает администратору понятную
картину по сенсорам.

## 2. Текущий рабочий стек

Актуальный стек honeypot-модулей:

| Модуль | Что изображает | Основные сервисы |
|---|---|---|
| `cowrie` | Linux-узел с SSH/Telnet | SSH, Telnet |
| `conpot` | промышленный/инженерный узел | Modbus, S7-like, BACnet, HTTP |
| `mailoney` | почтовый шлюз | SMTP |
| `honeypy` | набор простых сервисов | HTTP, MySQL, Redis, FTP, Telnet |
| `glutton` | мультисервисный сетевой honeypot | Docker API, MQTT, Kubernetes API, RDP, VNC, SIP |

Старый стек `opencanary`, `heralding`, `dionaea` удален из активного проекта.
Если в локальном `config/site.local.json` остались эти модули, такая policy
считается старой и не пройдет валидацию с текущим `catalog/honeypots.json`.

## 3. Архитектура

```text
                         HTTP/API
администратор ─────────────────────────► center:8080
                                           │
                                           │ policy + events
                                           ▼
                                     PostgreSQL

sensor-agent ── POST /api/sensors/<id>/sync ──► center
      │                                           ▲
      │ desired-state                            │ POST /api/events
      ▼                                           │
Docker-runtime ── docker compose ──► honeypot-контейнеры
      ▲                                           │
      └──────────── файлы логов runtime ◄─────────┘
```

Разделение ответственности:

| Компонент | Ответственность |
|---|---|
| Центр | policy, catalog, API, веб-страницы, события, состояние сенсоров |
| Сенсорный агент | sync с центром, выбор runtime, запуск runtime, status |
| Docker-runtime | генерация compose/configs, запуск контейнеров, чтение логов |
| Native-runtime | запасной легкий режим без контейнеров |
| Catalog | описание доступных модулей и сервисов |
| Policy | конкретные сенсоры, порты, профили и настройки стенда |

Центр не открывает honeypot-порты. Honeypot-порты открываются только на
сенсоре.

## 4. Текущее дерево проекта

```text
.
├── README.md
├── Makefile
├── compose.yml
├── pyproject.toml
├── requirements.txt
├── ansible/
├── catalog/
├── center/
├── config/
├── docs/
├── scripts/
├── sensor/
└── tools/
```

Назначение каталогов:

| Путь | Назначение |
|---|---|
| `ansible/` | установка центра и сенсоров на удаленные Linux-узлы |
| `catalog/` | каталог поддерживаемых honeypot-модулей |
| `center/` | центральный HTTP/API узел |
| `config/` | пример policy; локальная policy не хранится в git |
| `docs/` | этот документ |
| `scripts/` | shell-команды для сборки, запуска и диагностики |
| `sensor/` | sensor-agent и runtime-код |
| `tools/` | проверка policy и e2e smoke-тест |

## 5. Файлы верхнего уровня

| Файл | Назначение |
|---|---|
| `.dockerignore` | исключения при сборке Docker image центра |
| `.env.example` | пример переменных окружения |
| `.gitignore` | исключения git |
| `Makefile` | короткие команды разработки |
| `README.md` | короткий вход в проект |
| `compose.yml` | запуск центра и PostgreSQL |
| `pyproject.toml` | метаданные Python-проекта |
| `requirements.txt` | Python-зависимости |
| `ВКРТекст.md` | текст ВКР, не часть инженерной чистки |

## 6. Центр

Центр запускается как Python-приложение и обслуживает веб-страницы и API.

Основные файлы:

| Файл | Назначение |
|---|---|
| `center/main.py` | CLI: host, port, пути к policy/catalog/store |
| `center/app.py` | создание HTTP-сервера |
| `center/server.py` | серверная точка запуска |
| `center/api/handler.py` | все HTTP-маршруты |
| `center/core/auth.py` | Basic/Bearer авторизация |
| `center/core/overview.py` | сводка для интерфейса |
| `center/core/paths.py` | пути по умолчанию и лимиты |
| `center/core/policy.py` | валидация policy и desired-state |
| `center/core/profiles.py` | встроенные профили сенсоров |
| `center/core/sensor_sync.py` | обработка sync от agent |
| `center/core/utils.py` | JSON и время |
| `center/persistence/store.py` | PostgreSQL/SQLite подключение и миграции |
| `center/persistence/events.py` | запись, чтение, фильтрация и очистка событий |
| `center/web/views.py` | рендеринг HTML-шаблонов |
| `center/web/templates/admin.html` | настройки центра и сенсоров |
| `center/web/templates/database.html` | просмотр событий |
| `center/web/templates/mask.html` | настройки легенды honeypot |
| `center/Dockerfile` | Docker image центра |

## 7. API центра

Основные маршруты:

| Метод | Маршрут | Назначение |
|---|---|---|
| `GET` | `/health` | статус центра и policy |
| `GET` | `/settings` | основная веб-страница |
| `GET` | `/mask` | веб-страница маскировки |
| `GET` | `/db` | веб-страница базы событий |
| `GET` | `/api/modules` | catalog модулей |
| `GET` | `/api/profiles` | встроенные и policy-профили |
| `GET` | `/api/policy` | текущая policy |
| `PUT` | `/api/policy` | заменить policy |
| `PATCH` | `/api/site` | изменить site-настройки |
| `GET` | `/api/overview` | агрегированная сводка |
| `GET` | `/api/sensors` | список сенсоров и их состояние |
| `POST` | `/api/sensors` | добавить сенсор |
| `DELETE` | `/api/sensors/<id>` | удалить сенсор |
| `PATCH` | `/api/sensors/<id>/modules/<module>` | изменить модуль |
| `PATCH` | `/api/sensors/<id>/modules/<module>/services/<service>` | изменить сервис |
| `POST` | `/api/sensors/<id>/sync` | sync от sensor-agent |
| `POST` | `/api/sensors/<id>/apply-profile` | применить профиль |
| `POST` | `/api/events` | принять событие |
| `GET` | `/api/events` | получить события |
| `GET` | `/api/db/stats` | статистика БД |
| `POST` | `/api/db/purge` | очистить события |
| `POST` | `/api/mask` | сохранить настройки маскировки |

Для административных маршрутов используется авторизация из `center/core/auth.py`.
Лабораторный режим допускает Basic Auth или Bearer Token.

## 8. Хранение событий

По умолчанию `compose.yml` запускает PostgreSQL:

```text
edc-postgres
edc-center
```

Центр подключается к PostgreSQL через:

```text
CENTER_DB_DSN=postgresql://edc:edc@postgres:5432/edc
```

Если `CENTER_DB_DSN` не задан или не начинается с `postgres`, используется
SQLite fallback в `var/center/events.sqlite3`.

Таблица `events` содержит:

| Поле | Смысл |
|---|---|
| `id` | внутренний номер события |
| `received_at` | время приема центром |
| `timestamp` | время события от сенсора |
| `event_type` | тип события |
| `sensor_id` | сенсор |
| `module` | honeypot-модуль |
| `service` | сервис |
| `severity` | важность |
| `src_ip` | IP источника |
| `src_port` | порт источника |
| `dst_port` | порт назначения |
| `raw_sample` | короткий фрагмент |
| `raw_event` | исходный JSON |

## 9. Catalog и policy

`catalog/honeypots.json` описывает возможности системы: модули, сервисы,
порты контейнеров, порты по умолчанию и schema настроек.

`config/site.example.json` - пример рабочей policy. Из него создается
локальный `config/site.local.json`.

`config/site.local.json` не хранится в git, потому что в нем адреса,
конкретные сенсоры, рабочие порты и локальные эксперименты.

Создание локальной policy:

```bash
cp config/site.example.json config/site.local.json
python3 tools/validate_policy.py --policy config/site.local.json
```

Если файл принадлежит другому пользователю:

```bash
sudo chown "$USER":users config/site.local.json
```

## 10. Сенсорный агент

Главный файл:

```text
sensor/agent.py
```

Агент делает цикл:

1. Формирует sync payload.
2. Отправляет `POST /api/sensors/<sensor_id>/sync`.
3. Получает desired-state.
4. Запускает Docker-runtime или Native-runtime.
5. Собирает active services.
6. Отправляет status.
7. При изменении desired-state перезапускает runtime.
8. При остановке останавливает runtime.

Ручной запуск:

```bash
python3 sensor/agent.py \
  --center http://<center-ip>:8080 \
  --sensor-id banana-pi-pro-1 \
  --state-dir var/sensor \
  --serve \
  --interval 20
```

Разовый dry-run:

```bash
python3 sensor/agent.py \
  --center http://<center-ip>:8080 \
  --sensor-id banana-pi-pro-1 \
  --once
```

## 11. Docker-runtime

Файлы:

| Файл | Назначение |
|---|---|
| `sensor/runtime.py` | основной Docker-runtime |
| `sensor/runtime_configs.py` | генерация конфигов модулей |
| `sensor/runtime_helpers.py` | image map, ports, helpers |
| `sensor/runtime_status.py` | чтение состояния контейнеров |

Docker-runtime:

1. Проверяет Docker и Docker Compose.
2. Создает `state_dir/docker-runtime/`.
3. Копирует build context из `sensor/images/<module>/`.
4. Генерирует конфиги в `docker-runtime/<module>/config/`.
5. Генерирует `docker-compose.yml`.
6. Удаляет старые контейнеры с label `edc.sensor_id=<sensor_id>`.
7. Запускает контейнеры.
8. Читает логи из `docker-runtime/<module>/logs/`.
9. Преобразует строки логов в события и отправляет их в центр.

Docker-runtime не должен подменять реальные honeypot-проекты заглушками.

## 12. Dockerfiles honeypot-модулей

| Путь | Назначение |
|---|---|
| `sensor/images/cowrie/Dockerfile` | сборка Cowrie |
| `sensor/images/conpot/Dockerfile` | сборка Conpot |
| `sensor/images/mailoney/Dockerfile` | сборка Mailoney |
| `sensor/images/mailoney/entrypoint.sh` | запуск Mailoney |
| `sensor/images/honeypy/Dockerfile` | сборка HoneyPy |
| `sensor/images/honeypy/entrypoint.sh` | запуск HoneyPy |
| `sensor/images/glutton/Dockerfile` | сборка Glutton |

Если контейнер собирается, но не стартует, сначала смотреть:

```bash
docker ps -a
docker logs --tail 120 <container>
docker inspect <container> --format '{{json .State}}'
```

## 13. Native-runtime

Файл:

```text
sensor/native_runtime.py
```

Native-runtime открывает TCP-порты стандартной библиотекой Python и фиксирует
подключения. Это запасной режим для слабых ARMv7-узлов или ситуации, когда
реальные контейнеры временно не собраны.

Основной путь проекта - Docker-runtime. Native-runtime нужен как fallback и
для быстрых лабораторных проверок.

Включение в policy:

```json
"runtime_mode": "native"
```

Основной режим:

```json
"runtime_mode": "docker"
```

## 14. Профили сенсоров

Профили находятся в `center/core/profiles.py`.

Встроенные профили:

| Профиль | Назначение |
|---|---|
| `full_stack` | полный набор `cowrie/conpot/mailoney/honeypy/glutton` |
| `printer` | маска принтера/МФУ |
| `camera` | маска IP-камеры |
| `backup_server` | маска backup/storage сервера |

Профиль можно применить через API:

```bash
curl -X POST http://<center>:8080/api/sensors/<sensor-id>/apply-profile \
  -H 'Content-Type: application/json' \
  -d '{"profile_id":"full_stack"}'
```

## 15. Ansible

Ansible - это способ установки, а не часть runtime-логики.

Файлы:

| Файл | Назначение |
|---|---|
| `ansible/ansible.cfg` | настройки Ansible |
| `ansible/inventory.example.yml` | пример inventory |
| `ansible/group_vars/all.yml` | общие переменные |
| `ansible/playbooks/site.yml` | общий playbook |
| `ansible/playbooks/center.yml` | установка центра |
| `ansible/playbooks/classify_sensors.yml` | определение класса сенсора |
| `ansible/playbooks/sensors.yml` | установка sensor-agent |
| `ansible/playbooks/remove_sensor.yml` | удаление сенсора |

Запуск полного playbook:

```bash
cd ansible
ansible-playbook playbooks/site.yml --ask-pass --ask-become-pass
```

Удаление сенсора:

```bash
cd ansible
ansible-playbook playbooks/remove_sensor.yml \
  --limit banana-pi-pro-1 \
  --ask-pass \
  --ask-become-pass
```

Ручной запуск без Ansible допустим и часто проще для отладки.

## 16. Запуск центра

Первичный запуск:

```bash
cp config/site.example.json config/site.local.json
make up
```

Проверка:

```bash
curl http://127.0.0.1:8080/health
docker compose ps
docker compose logs -f center
```

Остановка:

```bash
make down
```

Прямой запуск без Docker:

```bash
python3 -m center.main --host 127.0.0.1 --port 8080
```

## 17. Сборка ARMv7 bundle

Скрипт сборки:

```bash
scripts/prebuild_armv7_bundle.sh 2>&1 | tee artifacts/build-armv7-$(date +%F-%H%M%S).log
```

Ожидаемый архив:

```text
artifacts/edc-armv7-images-YYYY-MM-DD-HHMMSS.tar.gz
```

Ожидаемые образы:

```text
edc/cowrie:local
edc/conpot:local
edc/mailoney:local
edc/honeypy:local
edc/glutton:local
```

Загрузка на сенсор:

```bash
docker load -i artifacts/edc-armv7-images-YYYY-MM-DD-HHMMSS.tar.gz
docker image ls --format 'table {{.Repository}}\t{{.Tag}}\t{{.Size}}' | grep '^edc/'
```

## 18. Проверка sensor runtime

На сенсоре:

```bash
sudo systemctl restart edc-sensor
sleep 20
sudo systemctl status edc-sensor --no-pager
journalctl -u edc-sensor -n 120 --no-pager
```

Контейнеры:

```bash
docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}' | grep edc
```

Порты:

```bash
ss -lntup | egrep '2222|2223|15020|10102|47808|8800|2525|8082|3307|6380|2124|2324|2375|1883|6443|3389|5900|5060'
```

Probe-тесты:

```bash
nc -vz <sensor-ip> 2222
nc -vz <sensor-ip> 2223
curl -v --max-time 5 http://<sensor-ip>:8800/
printf 'HELO test.local\r\n' | nc -w 5 <sensor-ip> 2525
curl -v --max-time 5 http://<sensor-ip>:8082/
printf 'INFO\r\n' | nc -w 5 <sensor-ip> 6380
```

События:

```bash
curl -sS 'http://127.0.0.1:8080/api/events?limit=100' > artifacts/events-after-docker-runtime.json
```

## 19. Что присылать при ошибках

Для сборки:

```text
artifacts/build-armv7-*.log
```

Для запуска:

```text
docker image ls по edc/*
docker ps -a по edc-контейнерам
journalctl -u edc-sensor -n 120 --no-pager
docker logs --tail 120 <упавший контейнер>
docker inspect <упавший контейнер> --format '{{json .State}}'
artifacts/events-after-docker-runtime.json
```

Для policy:

```bash
python3 tools/validate_policy.py --policy config/site.local.json
curl http://<center>:8080/health
```

## 20. Команды разработки

```bash
make help
make up
make down
make logs
make check
make e2e
make clean
```

`make check` проверяет:

- Python compile для `center`, `sensor`, `tools`;
- `config/site.example.json` против `catalog/honeypots.json`;
- `docker compose config`.

Локальная policy проверяется отдельно:

```bash
EDC_CHECK_LOCAL_POLICY=1 make check
```

Это сделано специально: `config/site.local.json` является рабочим файлом
стенда и может временно отличаться от чистого примера.

## 21. Тесты

Основной smoke-тест:

```bash
python3 tools/e2e_reconfigure_test.py
```

Он проверяет:

- запуск центра на случайном локальном порту;
- `/health`;
- `POST /api/sensors/<id>/sync`;
- отображение сенсора через `/api/sensors`;
- PATCH API для модулей и сервисов;
- генерацию Docker Compose для реального стека.

В некоторых песочницах тесту нужно право открыть локальный TCP socket.

## 22. Диагностика

Типовые проблемы:

| Симптом | Где смотреть | Вероятная причина |
|---|---|---|
| `/health` показывает `invalid_policy` | `tools/validate_policy.py` | policy не совпадает с catalog |
| Сенсор не регистрируется | `journalctl -u edc-sensor` | неверный URL центра или sensor_id |
| Нет контейнеров | `docker compose`, `docker ps -a` | Docker недоступен или compose не сгенерирован |
| Контейнер exited | `docker logs` | ошибка Dockerfile, entrypoint или конфига |
| Порт не слушается | `ss -lntup` | сервис отключен, контейнер упал, порт занят |
| Нет событий | логи модуля и `/api/events` | модуль не пишет лог или runtime не читает нужный файл |
| ARMv7 build failed | build log | upstream-зависимость не собирается под ARMv7 |

Полезные скрипты:

```bash
scripts/center_sensor_audit.sh http://<center>:8080
scripts/sensor_doctor.sh banana-pi-pro-1
scripts/run_sensor_runtime.sh
```

## 23. Правила чистоты проекта

В git должны храниться:

- исходный код;
- Dockerfiles;
- примерная policy;
- catalog;
- Ansible playbooks;
- единая документация;
- тесты и скрипты.

В git не должны храниться:

```text
artifacts/
var/
__pycache__/
*.pyc
config/site.local.json
config/site.local.json.bak-*
ВКРТекст.md
```

`README.md` оставлен коротким специально. Подробности должны быть здесь, а не
размазаны по нескольким устаревающим файлам.

## 24. Что было удалено при чистке

Удалены устаревшие и дублирующие документы:

```text
docs/architecture.md
docs/beginner_guide.md
docs/docker_honeypot_test_plan.md
docs/file_map.md
docs/network.md
docs/references.md
docs/roadmap.md
docs/test_stand.md
catalog/README.md
center/README.md
sensor/README.md
```

Удалены локальные временные файлы:

```text
center/1.txt
sensor/1.txt
config/site.local.json.bak-old-stack
artifacts/edc-armv7-images-2026-05-14-202946.tar.gz
```

Причина удаления: эти файлы либо дублировали данный документ, либо описывали
старый стек, либо были локальными артефактами.

## 25. Минимальный путь нового разработчика

1. Открыть `README.md`.
2. Перейти в `docs/system_guide_ru.md`.
3. Прочитать разделы 1-13.
4. Скопировать `config/site.example.json` в `config/site.local.json`.
5. Выполнить `make check`.
6. Запустить центр `make up`.
7. Собрать или загрузить Docker-образы сенсора.
8. Запустить sensor-agent.
9. Сделать probe-тесты.
10. Посмотреть события в `/db` или `/api/events`.

Если этот путь проходит, проект находится в рабочем состоянии.
