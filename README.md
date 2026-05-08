# Early Detection Complex

Распределённый комплекс раннего обнаружения подозрительной сетевой активности на основе honeypot.

## Что Сейчас Главное

Центр управляет сенсорами. Пользователь открывает веб-интерфейс, вводит IP платы, SSH-логин и пароль, нажимает **Установить / обновить**. Центр сам копирует sensor-agent, ставит Docker на плате, создаёт systemd-сервис и запускает реальные honeypot-контейнеры.

## Запуск Центра

Проще всего:

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

## Что Нужно На Плате

Минимум:

```text
ОС Linux + сеть + SSH + пользователь с sudo или root
```

Docker вручную ставить не нужно. Центр установит его сам.

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
```

Старые прототипы и сгенерированные runtime-файлы больше не хранятся в git.

## Honeypot Runtime

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
python3 -m compileall center sensor tools
python3 tools/validate_policy.py
python3 tools/e2e_reconfigure_test.py
docker compose config
```
