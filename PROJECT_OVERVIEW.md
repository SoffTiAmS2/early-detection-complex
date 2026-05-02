# Кратко о проекте

`early-detection-complex` - это прототип комплекса раннего обнаружения подозрительной сетевой активности. Он использует honeypot/deception-сенсоры: если кто-то подключается к портам-приманкам, сенсор фиксирует событие и отправляет его в центральный узел.

## Из чего состоит

- `central-node` - центральный HTTP API, прием событий, хранение JSONL, dashboard.
- `containers/fake-services` - встроенные сервисы-приманки: SSH-like, HTTP-like, FTP-like, SMTP-like и другие.
- `containers/log-agent` - агент, который отправляет локальные события сенсора в центр.
- `containers/display-agent` - агент статуса сенсора.
- `orchestrator/generate.py` - генератор конфигураций сенсоров.
- `manager` - web-конфигуратор профилей, IP, сервисов и маскировки.
- `inventory/project.json` - главный файл настройки проекта.
- `sensors/<sensor>` - готовые директории сенсоров с `docker-compose.yml`.

## Быстрый запуск

```sh
cd /home/shizik/Yandex.Disk/early-detection-complex
scripts/generate_sensor.sh
cd central-node
docker compose up -d --build
cd ../sensors/sensor1
docker compose up -d --build
```

## Web-конфигуратор

```sh
cd /home/shizik/Yandex.Disk/early-detection-complex
scripts/start_manager.sh
```

Открыть:

```text
http://127.0.0.1:8090
```

## Проверка

```sh
curl http://127.0.0.1:8080/health
curl http://127.0.0.1:8080/api/sensors | python3 -m json.tool
printf 'test\r\n' | nc -w 2 127.0.0.1 2222
tail -n 20 sensors/sensor1/logs/events.jsonl
```

Dashboard:

```text
http://<central-ip>:8080/dashboard
```

## Что менять чаще всего

Главный файл:

```text
inventory/project.json
```

В нем меняются:

- IP центрального узла;
- IP сенсоров;
- профиль сенсора;
- список сервисов-приманок;
- параметры маскировки.

После изменения:

```sh
scripts/generate_sensor.sh
```

## Где подробная документация

- `README.md` - основное описание для работы с проектом.
- `docs/full_report.md` - ссылка на полный отчет.
- `docs/deployment.md` - развертывание.
- `docs/architecture.md` - архитектура.
- `docs/web_configurator.md` - web-конфигуратор.

Полные материалы для ВКР лежат в:

```text
/home/shizik/Yandex.Disk/Document/Obsidian Vault/ВКР/Документация_early_detection_complex
```
