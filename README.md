# Early Detection Complex

Распределенный комплекс раннего выявления подозрительной сетевой активности на базе honeypot/deception-сенсоров.

Главная идея: центральный узел запускается как Docker stack, а сенсорные платы готовятся центром по SSH. На плате заранее нужны только ОС, сеть и SSH-доступ; Docker, конфигурацию и контейнеры ставит центр.

Web-морда временно убрана в архив. Сейчас основной фокус проекта - надежная установка и настройка honeypot на сенсорах через API/CLI.

## Что Внутри

```text
center/              # collector, API-manager, генератор, Ansible и Docker Compose stack центра
sensor/              # агенты сенсора: доставка логов и локальный статус
config/              # tracked-конфигурация проекта
scripts/             # запуск центра и dev helpers
docs/                # вспомогательная документация
archive/             # отложенный web-интерфейс
```

`sensors/` не хранится в git. Он генерируется локально из `config/project.json`.

## Быстрый Запуск Центра

```sh
scripts/install_central.sh
```

После запуска:

```text
http://<central-ip>:8090            # manager API
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

Дальше все делается командой с центрального узла:

```sh
EDC_CENTER_URL=http://127.0.0.1:8090 scripts/deploy_sensor.sh sensor1 <sensor-ip> root 22
```

Центр сгенерирует конфигурацию, поставит Docker на плату, скопирует нужные файлы и запустит контейнеры сенсора.
Прогресс установки, текущий шаг Ansible и последняя строка вывода отображаются прямо в терминале.

## Основные Компоненты

- `center/collector/server.py` принимает события, хранит JSONL и отдает API.
- `center/manager/backend/server.py` обслуживает API, job-статусы и Ansible-деплой.
- `center/orchestrator/generate.py` читает `config/project.json` и создает локальные `sensors/<name>/`.
- `center/ansible/deploy_sensor.yml` устанавливает/обновляет выбранный сенсор по SSH.
- `sensor/Dockerfile` собирает единый образ `edc-sensor` из Python slim и Cowrie source checkout, чтобы образ работал на ARM-платах без зависимости от amd64-only Docker manifest.
- внутри `edc-sensor` запускаются Cowrie, sensor-node, log-agent и display-agent.
- `sensor-node` отправляет `sensor.status`, пишет локальный `state/sensor_status.json` и фиксирует ранние `sensor.connection_seen` события по managed TCP-портам.

## Конфигурация

Основной tracked-файл:

```text
config/project.json
```

В нем задаются:

- сеть и IP центрального узла;
- список сенсоров;
- роль сенсора;
- honeypot: сейчас реально поддержан `cowrie`;
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
printf 'admin\r\n' | nc -w 2 <sensor-ip> 2223
```

События должны появиться в:

```text
http://<central-ip>:8080/api/events
```

## Dev Режим

Локальный запуск manager без Docker нужен только для разработки API:

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
- Пароли, переданные в deploy API или `scripts/deploy_sensor.sh`, используются только для текущего Ansible-запуска и не сохраняются в `config/project.json`.
- `.env`, `sensors/`, logs и `events.jsonl` игнорируются git.

## Документация

- `docs/deployment.md` - установка и эксплуатация.
- `docs/architecture.md` - архитектура.
- `docs/file_map.md` - значение каждого tracked-файла.
- `docs/honeypot_installation.md` - как центр устанавливает и настраивает honeypot на сенсоре.
- `docs/deception_masking.md` - логика маскировки.
- `docs/honeypot_catalog.md` - справочник honeypot, сервисов и настроек.
- `docs/honeypot_integration_plan.md` - качественный план подключения OpenCanary, Conpot, Dionaea и Heralding без фейковых пунктов в UI.
- `docs/functions_io.md` - функции, входы и выходы компонентов.
- `docs/full_report.md` - ссылки на полный отчет ВКР.
