# Early Detection Complex / Комплекс Раннего Обнаружения

Распределённый комплекс раннего обнаружения подозрительной сетевой активности на основе honeypot.

## Что Сейчас Главное

Центр управляет сенсорами. Пользователь открывает веб-интерфейс, вводит IP платы, SSH-логин и пароль, нажимает **Установить / обновить**. Центр сам копирует sensor-agent, ставит Docker на плате, создаёт systemd-сервис и запускает реальные honeypot-контейнеры.

## Запуск Центра

Проще всего:

```sh
make up
```

Если `make` не установлен:

```sh
docker compose up -d --build
```

После запуска:

```text
http://<ip-центра>:8080
```

Локально без Docker:

```sh
python3 -m center.main --host 0.0.0.0 --port 8080
```

Для установки сенсоров из локального запуска на центре должны быть пакеты `openssh-client` и `sshpass`. Docker-образ центра уже содержит их.

Для первого знакомства смотри [docs/beginner_guide.md](docs/beginner_guide.md).

Рабочая политика центра хранится в `config/site.local.json`. Если файла нет, центр при первом запуске скопирует его из `config/site.example.json`.

## Что Нужно На Плате

Минимум:

```text
ОС Linux + сеть + SSH + пользователь с sudo или root
```

Поддерживается установка на Banana Pi Pro с Armbian. Docker вручную ставить не нужно: центр установит Python, Docker, Compose и `edc-sensor.service` сам.

На 32-bit ARM часть тяжёлых honeypot images может не иметь подходящего Docker-образа. В этом случае sensor-agent пропустит неподдержанный модуль и отправит предупреждение в status.

## Структура

```text
center/     # отдельное Python-приложение центра
sensor/     # agent и Docker runtime, которые запускаются на плате
catalog/    # описание поддерживаемых honeypot-модулей и их настроек
config/     # политика стенда: сенсоры, профили, порты, persona
scripts/    # локальные helper-скрипты
tools/      # проверки политики и e2e reconfigure-тест
docs/       # архитектура, карта файлов, стенд, roadmap
compose.yml # контейнер центра
Makefile    # короткие команды запуска и проверки
pyproject.toml, requirements.txt # упаковка Python-проекта, зависимостей нет
```

Старые прототипы и сгенерированные runtime-файлы больше не хранятся в git.

## Honeypot Runtime / Запуск Honeypot

Сенсор не имитирует протоколы сам. Он запускает реальные upstream Docker images:

```text
Cowrie     cowrie/cowrie:latest
OpenCanary thinkst/opencanary:latest
Dionaea    dinotools/dionaea:latest
Conpot     honeynet/conpot:latest
Heralding  dtagdevsec/heralding:24.04.1
```

Sensor-agent удаляет старые контейнеры комплекса с label `edc.sensor_id=<sensor_id>`, применяет новую конфигурацию, читает `docker logs` и отправляет сырые события в центр.

## Проверки

```sh
make check
python3 tools/e2e_reconfigure_test.py
```
