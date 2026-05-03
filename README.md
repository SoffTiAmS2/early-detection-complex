# Early Detection Complex

Распределенный комплекс раннего выявления подозрительной сетевой активности на базе honeypot/deception-сенсоров.

Главная идея: центральный узел запускается как Docker stack, а сенсорные платы готовятся из web-консоли по SSH. На плате заранее нужны только ОС, сеть и SSH-доступ; Docker, конфигурацию и контейнеры ставит центр.

## Что Внутри

```text
center/              # collector, web-консоль, генератор, Ansible и Docker Compose stack центра
sensor/              # контейнеры, которые устанавливаются на сенсорную плату
config/              # tracked-конфигурация проекта
scripts/             # запуск центра и dev helpers
docs/                # вспомогательная документация
```

`sensors/` не хранится в git. Он генерируется локально из `config/project.json`.

## Быстрый Запуск Центра

```sh
scripts/install_central.sh
```

После запуска:

```text
http://<central-ip>:8090            # web-консоль управления
http://<central-ip>:8080/health     # health API
http://<central-ip>:8080/api/events # события collector
```

`install_central.sh` ставит Docker/Compose на центральный узел и запускает `center/docker-compose.yml`.

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
3. Укажи IP, выбери honeypot, затем сервисы и настройки внутри него.
4. В блоке `Установка/обновление по SSH` введи SSH-доступ.
5. Нажми `Установить/обновить`.

Центр сгенерирует конфигурацию, поставит Docker на плату, скопирует нужные файлы и запустит контейнеры сенсора.
Прогресс установки, текущий шаг Ansible, вывод и кнопка отмены отображаются в web-консоли.

## Основные Компоненты

- `center/collector/server.py` принимает события, хранит JSONL и отдает API.
- `center/manager/backend/server.py` обслуживает web-консоль, job-статусы и Ansible-деплой.
- `center/orchestrator/generate.py` читает `config/project.json` и создает локальные `sensors/<name>/`.
- `center/ansible/deploy_sensor.yml` устанавливает/обновляет выбранный сенсор по SSH.
- `sensor/containers/fake-services` открывает TCP-порты-приманки и пишет события.
- `sensor/containers/log-agent` доставляет события в центр.
- `sensor/containers/display-agent` показывает локальный статус сенсора.

## Конфигурация

Основной tracked-файл:

```text
config/project.json
```

В нем задаются:

- сеть и IP центрального узла;
- список сенсоров;
- роль сенсора;
- дерево honeypot: `opencanary`, `cowrie`, `heralding`, `conpot`, `dionaea`, `honeytrap`;
- сервисы и настройки внутри каждого выбранного honeypot;
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
```

## Dev Режим

Локальный запуск manager без Docker нужен только для разработки:

```sh
scripts/start_manager.sh
```

Проверка compose-конфигурации центра:

```sh
cd center
docker compose config
```

## Безопасность

- SSH-доступ к платам должен быть в management-сети, не в атакующем сегменте.
- Пароли, введенные в web-консоли для деплоя, используются только для текущего Ansible-запуска и не сохраняются в `config/project.json`.
- `.env`, `sensors/`, logs и `events.jsonl` игнорируются git.

## Документация

- `docs/deployment.md` - установка и эксплуатация.
- `docs/architecture.md` - архитектура.
- `docs/deception_masking.md` - логика маскировки.
- `docs/honeypot_catalog.md` - справочник honeypot, сервисов и настроек.
- `docs/web_configurator.md` - web-консоль и API.
- `docs/functions_io.md` - функции, входы и выходы компонентов.
- `docs/full_report.md` - ссылки на полный отчет ВКР.
