# Early Detection Complex

Распределенный комплекс раннего выявления подозрительной сетевой активности на базе honeypot/deception-сенсоров.

Главная идея: центральный узел запускается как Docker stack, а сенсорные платы готовятся из web-консоли по SSH. На плате заранее нужны только ОС, сеть и SSH-доступ; Docker, конфигурацию и контейнеры ставит центр.

## Что Внутри

```text
central-node/        # collector, dashboard API и Docker Compose stack центра
manager/             # web-консоль управления, генерации и SSH-деплоя
ansible/             # playbook установки/обновления сенсора по SSH
containers/          # сервисы, запускаемые на сенсорной плате
orchestrator/        # генератор конфигураций из inventory/project.json
inventory/           # tracked источник конфигурации проекта
scripts/             # запуск центра и dev helpers
docs/                # вспомогательная документация
```

`sensors/`, `inventory/network.yml` и `inventory/sensors.yml` не хранятся в git. Они генерируются локально из `inventory/project.json`.

## Быстрый Запуск Центра

```sh
scripts/install_central.sh
```

После запуска:

```text
http://<central-ip>:8090            # web-консоль управления
http://<central-ip>:8080/dashboard  # dashboard событий
http://<central-ip>:8080/health     # health API
```

`install_central.sh` ставит Docker/Compose на центральный узел и запускает `central-node/docker-compose.yml`.

## Подготовка Сенсорной Платы

На плате нужно сделать только базовую подготовку:

- установить Debian/Armbian;
- подключить плату к сети;
- включить SSH;
- иметь пользователя `root` или пользователя с `sudo`;
- знать IP, SSH port, login и password.

Дальше все делается из web-консоли:

1. Открой `http://<central-ip>:8090`.
2. Добавь или выбери сенсор.
3. Укажи IP, профиль, сервисы-приманки и маскировку.
4. В блоке `Установка/обновление по SSH` введи SSH-доступ.
5. Нажми `Установить/обновить`.

Центр сгенерирует конфигурацию, поставит Docker на плату, скопирует нужные файлы и запустит контейнеры сенсора.

## Основные Компоненты

- `central-node/ingest/server.py` принимает события, хранит JSONL и отдает dashboard/API.
- `manager/backend/server.py` обслуживает web-консоль, запускает генератор и Ansible-деплой.
- `orchestrator/generate.py` читает `inventory/project.json` и создает локальные `sensors/<name>/`.
- `ansible/deploy_sensor.yml` устанавливает/обновляет выбранный сенсор по SSH.
- `containers/fake-services` открывает TCP-порты-приманки и пишет события.
- `containers/log-agent` доставляет события в центр.
- `containers/display-agent` показывает локальный статус сенсора.

## Конфигурация

Основной tracked-файл:

```text
inventory/project.json
```

В нем задаются:

- сеть и IP центрального узла;
- список сенсоров;
- роль сенсора;
- профиль: `opencanary`, `cowrie`, `heralding`, `conpot`, `dionaea`, `honeytrap`;
- сервисы-приманки;
- маскировка: hostname, OS, department, asset tag, notes.

Сгенерировать конфигурации вручную для отладки:

```sh
scripts/generate_sensor.sh
```

## Проверка

Центр:

```sh
curl http://127.0.0.1:8080/health
curl http://127.0.0.1:8080/api/sensors | python3 -m json.tool
```

После установки сенсора можно проверить порты-приманки с другой машины в той же сети:

```sh
printf 'admin\r\n' | nc -w 2 <sensor-ip> 2222
printf 'GET /admin HTTP/1.0\r\n\r\n' | nc -w 2 <sensor-ip> 8081
```

События должны появиться в:

```text
http://<central-ip>:8080/api/events
http://<central-ip>:8080/dashboard
```

## Dev Режим

Локальный запуск manager без Docker нужен только для разработки:

```sh
scripts/start_manager.sh
```

Проверка compose-конфигурации центра:

```sh
cd central-node
docker compose config
```

## Безопасность

- SSH-доступ к платам должен быть в management-сети, не в атакующем сегменте.
- Пароли, введенные в web-консоли для деплоя, используются только для текущего Ansible-запуска и не сохраняются в `inventory/project.json`.
- `.env`, `sensors/`, logs и `events.jsonl` игнорируются git.

## Документация

- `docs/deployment.md` - установка и эксплуатация.
- `docs/architecture.md` - архитектура.
- `docs/deception_masking.md` - логика маскировки.
- `docs/web_configurator.md` - web-консоль и API.
- `docs/full_report.md` - ссылки на полный отчет ВКР.
