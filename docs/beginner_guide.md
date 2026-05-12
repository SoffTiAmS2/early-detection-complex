# Руководство Для Начинающих

Этот проект состоит из двух частей:

- `center/` - сервер управления. Он показывает веб-интерфейс, хранит политику, принимает события и устанавливает сенсоры по SSH.
- `sensor/` - агент сенсора. Он запускается на удаленной машине, забирает настройки из центра и поднимает honeypot-контейнеры через Docker.

Сетевая схема и порты описаны в [network.md](network.md).

## Быстрый Запуск Центра

Из корня проекта:

```sh
make up
```

То же самое без Makefile:

```sh
docker compose up -d --build
```

Открыть интерфейс:

```text
http://localhost:8080
```

Логи центра:

```sh
make logs
```

Остановить:

```sh
make down
```

## Как Установить Сенсор

1. Запусти центр.
2. Открой веб-интерфейс.
3. Введи IP сенсора, SSH-логин, SSH-пароль, рабочую папку и `sensor_id`.
4. Нажми "Установить / обновить".

Центр сам:

- добавит сенсор в политику;
- проверит SSH;
- скопирует `sensor/agent.py` и `sensor/runtime.py`;
- поставит Docker на сенсор, если его нет;
- создаст `edc-sensor.service`;
- запустит агент сенсора.

Для Banana Pi Pro / Armbian используй обычного пользователя с sudo-доступом. Docker заранее ставить не нужно.

Рабочие изменения политики пишутся в `config/site.local.json`. Файл `config/site.example.json` остается примером.

## Где Смотреть Логи

Логи центра:

```sh
docker logs -f edc-center
```

Логи агента на сенсоре:

```sh
journalctl -u edc-sensor.service -f
```

Honeypot-события на центре:

```sh
curl 'http://localhost:8080/api/events?limit=20' | python3 -m json.tool
```

## Простая Карта Кода

```text
center/main.py               запуск сервера
center/app.py                создание HTTP-сервера
center/api/handler.py        HTTP API центра
center/core/policy.py        проверка политики и desired-state
center/core/overview.py      сводка состояния сенсоров
center/core/metrics.py       Prometheus metrics
center/persistence/events.py SQLite-события
ansible/playbooks/           установка, классификация и удаление узлов
sensor/agent.py              цикл работы сенсора
sensor/runtime.py            Docker Compose для honeypot-контейнеров
```

## Проверка Перед Изменениями

```sh
make check
```

Более глубокая проверка API и генерации Docker runtime:

```sh
make e2e
```
