# Early Detection Complex

Распределенный комплекс раннего выявления подозрительной сетевой активности на базе конфигурируемых honeypot/deception-сенсоров.

Проект сделан для ВКР и демонстрирует полный цикл:

- настройка сенсорных узлов;
- выбор профиля и сервисов-приманок;
- маскировка сенсора под правдоподобный сетевой актив;
- установка и обновление сенсоров с центрального узла по SSH;
- запуск контейнеров на Banana Pi Pro или другой Debian/Armbian-системе без ручной настройки Docker на сенсоре;
- локальная запись событий;
- отправка событий на центральный узел;
- просмотр событий через API и dashboard.

Если нужен самый короткий обзор для нового участника, см. `PROJECT_OVERVIEW.md`.

## Что это такое

Комплекс состоит из центрального узла и набора сенсоров.

Сенсор - это отдельное устройство или VM, которое открывает порты-приманки. Если кто-то подключается к этим портам, событие считается подозрительным и отправляется в центральный узел.

Центральный узел принимает события, хранит их в JSONL и показывает через HTTP API или простую web-страницу.

Упрощенная схема:

```text
attacker/client -> sensor honeypot ports -> local events.jsonl -> log-agent -> central-node -> dashboard/API
```

## Зачем используются одноплатники

Одноплатные компьютеры, например Banana Pi Pro, используются как физические сенсорные узлы. Их можно поставить в нужный VLAN или сетевой сегмент: DMZ, офис, IoT, OT/технологический сегмент, бухгалтерия.

Это лучше отражает задачу распределенного раннего обнаружения, чем один сервер с набором VM. Сервер и виртуалки тоже можно использовать, но они хуже показывают физическое распределение сенсоров и становятся общей точкой отказа.

Switch с Docker также не выбран как основная площадка, потому что switch является критичной сетевой инфраструктурой. Honeypot принимает подозрительный трафик, поэтому его безопаснее размещать на отдельном некритичном сенсоре.

Подробное обоснование:

```text
/home/shizik/Yandex.Disk/Document/Obsidian Vault/ВКР/Документация_early_detection_complex/12_обоснование_выбора_одноплатников.md
```

## Основные возможности

- Несколько сенсоров с разными ролями.
- Настройка IP центрального узла и IP сенсоров.
- Выбор профиля: `opencanary`, `cowrie`, `heralding`, `conpot`, `dionaea`, `honeytrap`.
- Выбор сервисов-приманок checkbox-ами в web-конфигураторе.
- Маскировка через hostname, OS, department, asset tag и notes.
- Генерация готовых `docker-compose.yml` для сенсоров.
- Локальные JSONL-логи на сенсоре.
- Пересылка событий в центральный узел.
- Dashboard: `http://<central-ip>:8080/dashboard`.
- Web-консоль управления: `http://<central-ip>:8090`.
- Установка/обновление сенсоров из центра через Ansible по SSH.
- Проверка работоспособности через shell-скрипты.

## Почему не T-Pot

`T-Pot` намеренно не используется. Это готовая крупная платформа/кластер honeypot-ов. Для этой ВКР нужен управляемый легкий комплекс, где можно объяснить архитектуру, генерацию профилей, маскировку и работу отдельных сенсоров на Banana Pi Pro.

Проект допускает подключение разных honeypot-ов, но не строится вокруг монолитной готовой платформы.

## Структура проекта

```text
central-node/
  ingest/
    server.py              # центральный HTTP API, прием событий, dashboard
    Dockerfile
  docker-compose.yml       # запуск центрального узла
  storage/                 # локальное хранилище событий

containers/
  fake-services/           # встроенные TCP-сервисы-приманки
  log-agent/               # агент отправки логов на центральный узел
  display-agent/           # агент статуса сенсора
  cowrie/                  # место под будущий реальный Cowrie-профиль
  opencanary/              # место под будущий реальный OpenCanary-профиль

inventory/
  project.json             # главный файл конфигурации сети и сенсоров
  network.yml              # совместимый упрощенный inventory
  sensors.yml              # совместимый упрощенный inventory

manager/
  backend/server.py        # backend web-конфигуратора
  frontend/                # HTML/CSS/JS web-интерфейс
  cli.py                   # CLI-конфигуратор

ansible/
  deploy_sensor.yml        # установка/обновление сенсора с центра по SSH

orchestrator/
  generate.py              # генератор sensor1/sensor2/sensor3

scripts/
  bootstrap_clean.sh       # установка на чистую систему
  configure.sh             # CLI-настройка
  generate_sensor.sh       # генерация конфигураций
  install_central.sh       # установка Docker и запуск центральной web-консоли
  install_sensor.sh        # установка сенсора
  start_manager.sh         # web-конфигуратор
  start_sensor.sh          # запуск сенсора
  stop_sensor.sh           # остановка сенсора
  health_check.sh          # проверка состояния

sensors/
  sensor1/
  sensor2/
  sensor3/                 # сгенерированные директории сенсоров

docs/
  architecture.md
  deployment.md
  deception_masking.md
  full_report.md
  web_configurator.md
```

## Компоненты

### central-node

Центральный узел принимает события от сенсоров.

Маршруты:

```text
GET  /health
GET  /api/events
GET  /api/sensors
GET  /dashboard
POST /api/events
```

Хранилище:

```text
central-node/storage/events.jsonl
```

### fake-services

Встроенный безопасный honeypot-слой. Он открывает выбранные TCP-порты, отправляет баннеры и записывает события.

Примеры портов:

```text
2222  ssh
2323  telnet
8081  http
2121  ftp
2525  smtp
33060 mysql
1502  modbus
9100  printer
```

### log-agent

Читает:

```text
sensors/<sensor>/logs/events.jsonl
```

и отправляет события на:

```text
http://<central-ip>:8080/api/events
```

Также отправляет heartbeat, чтобы центр видел, что сенсор жив.

### display-agent

Проверяет связь с центральным узлом. Сейчас работает как консольный агент статуса. Позже его можно связать с I2C LCD 16x2 или LED-индикацией.

### orchestrator

`orchestrator/generate.py` читает:

```text
inventory/project.json
```

и генерирует:

```text
sensors/<sensor>/.env
sensors/<sensor>/docker-compose.yml
sensors/<sensor>/README.md
sensors/<sensor>/config/services.json
```

## Главный конфигурационный файл

Основная настройка находится здесь:

```text
inventory/project.json
```

Пример:

```json
{
  "network": {
    "subnet": "192.168.10.0/24",
    "gateway": "192.168.10.1",
    "central_node": "192.168.10.2"
  },
  "sensors": [
    {
      "name": "sensor1",
      "host": "192.168.10.11",
      "role": "dmz",
      "profile": "opencanary",
      "services": ["ssh", "http", "ftp", "smtp"],
      "mask": {
        "hostname": "dmz-backup-gw",
        "os": "Debian GNU/Linux 13",
        "department": "DMZ",
        "asset_tag": "DMZ-BAK-01",
        "notes": "external-facing decoy node"
      }
    }
  ]
}
```

## Быстрый старт центра

Из корня проекта:

```sh
cd /home/shizik/Yandex.Disk/early-detection-complex
scripts/install_central.sh
```

Открыть web-консоль:

```text
http://<central-ip>:8090
```

Открыть dashboard событий:

```text
http://<central-ip>:8080/dashboard
```

На сенсорной плате вручную нужна только ОС и SSH. В web-консоли выбери сенсор, укажи IP, профиль, сервисы и SSH-доступ, затем нажми `Установить/обновить`.

## Локальный режим разработки

Если нужно запускать manager без контейнера:

```sh
scripts/start_manager.sh
```

Проверить:

```sh
curl http://127.0.0.1:8080/health
```

## Запуск на Banana Pi Pro

На проверенной плате проект был развернут так:

```text
user: banana
host: 192.168.0.239
path: /home/banana/early-detection-complex
OS: Armbian/Debian 13
```

Проверка Docker на центральном узле:

```sh
docker --version
docker compose version
systemctl is-active docker
```

Ожидаемо:

```text
active
```

Запуск центра на плате:

```sh
cd /home/banana/early-detection-complex
scripts/install_central.sh
```

Сенсоры после этого устанавливаются из web-консоли центра по SSH.

## Проверка работоспособности

Проверить контейнеры сенсора:

```sh
cd /home/banana/early-detection-complex/sensors/sensor1
docker compose ps
```

Должны быть `Up`:

```text
fake-services
log-agent
display-agent
```

Проверить SSH-like honeypot:

```sh
printf 'admin\r\n' | nc -w 2 127.0.0.1 2222
```

Проверить HTTP-like honeypot:

```sh
printf 'GET /admin HTTP/1.0\r\n\r\n' | nc -w 2 127.0.0.1 8081
```

Проверить FTP-like honeypot:

```sh
printf 'USER test\r\n' | nc -w 2 127.0.0.1 2121
```

Проверить SMTP-like honeypot:

```sh
printf 'EHLO test.local\r\n' | nc -w 2 127.0.0.1 2525
```

Проверить локальные события:

```sh
tail -n 20 /home/banana/early-detection-complex/sensors/sensor1/logs/events.jsonl
```

Проверить центральный API:

```sh
curl http://127.0.0.1:8080/health
curl http://127.0.0.1:8080/api/events | python3 -m json.tool
curl http://127.0.0.1:8080/api/sensors | python3 -m json.tool
```

Dashboard:

```text
http://192.168.0.239:8080/dashboard
```

## Безопасная имитация атаки

Выполнять только против своих стендовых сенсоров.

```sh
printf 'root\r\n123456\r\n' | nc -w 2 192.168.0.239 2222
printf 'GET /wp-login.php HTTP/1.1\r\nHost: decoy.local\r\nUser-Agent: sqlmap/1.7\r\n\r\n' | nc -w 2 192.168.0.239 8081
printf 'GET /../../etc/passwd HTTP/1.1\r\nHost: decoy.local\r\nUser-Agent: curl/8.0\r\n\r\n' | nc -w 2 192.168.0.239 8081
printf 'USER backup\r\nPASS backup123\r\n' | nc -w 2 192.168.0.239 2121
printf 'EHLO attacker.local\r\nMAIL FROM:<test@evil.local>\r\nRCPT TO:<admin@company.local>\r\n' | nc -w 2 192.168.0.239 2525
```

После этого проверить:

```sh
curl http://192.168.0.239:8080/api/events | python3 -m json.tool
```

В событиях должны появиться `source_ip`, `service`, `protocol`, `payload_preview`, `sensor`, `role`, `profile` и `mask`.

## Проверенный результат

На Banana Pi Pro была выполнена проверка:

```text
central-node: работает на 8080
sensor1: работает
honeypot ports: 2222, 8081, 2121, 2525
events: события доходят до central-node
external source_ip: фиксируется при подключении с другой машины
```

Пример внешнего события:

```text
source_ip: 192.168.0.121
service: http
payload_preview: GET /external-check HTTP/1.1
profile: opencanary
role: dmz
mask.hostname: dmz-backup-gw
```

## Важное замечание по безопасности

Порт `22` на Banana Pi - настоящий SSH для управления, а не honeypot. В реальном стенде его лучше закрыть от атакующей сети и оставить только в management VLAN.

Honeypot-порты должны быть видны атакующему сегменту. Административные порты платы - нет.

## Где читать подробности

Краткая проектная документация:

```text
docs/architecture.md
docs/deployment.md
docs/deception_masking.md
docs/web_configurator.md
docs/full_report.md
```

Полный отчет для ВКР:

```text
/home/shizik/Yandex.Disk/Document/Obsidian Vault/ВКР/Документация_early_detection_complex/10_полный_отчет_о_реализации.md
```

Инструкция по эксплуатации:

```text
/home/shizik/Yandex.Disk/Document/Obsidian Vault/ВКР/Документация_early_detection_complex/11_инструкция_по_эксплуатации.md
```

Обоснование выбора одноплатников:

```text
/home/shizik/Yandex.Disk/Document/Obsidian Vault/ВКР/Документация_early_detection_complex/12_обоснование_выбора_одноплатников.md
```

## Минимальная команда для проверки стенда

```sh
cd /home/banana/early-detection-complex
curl http://127.0.0.1:8080/health
cd sensors/sensor1
docker compose ps
printf 'test\r\n' | nc -w 2 127.0.0.1 2222
tail -n 5 logs/events.jsonl
curl http://127.0.0.1:8080/api/sensors | python3 -m json.tool
```

Если эти команды проходят, базовый стенд работает.
