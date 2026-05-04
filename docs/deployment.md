# Deployment

## Требования

- Центральный узел: Debian/Armbian с доступом к интернету.
- Сенсорная плата: Debian/Armbian, сеть и включенный SSH.
- На сенсор заранее не нужно ставить Docker или копировать проект.

## Центральный Узел

Из корня проекта:

```sh
scripts/install_central.sh
```

Скрипт ставит Docker/Compose, включает Docker и запускает:

- `collector` на `8080`;
- `manager` на `8090`.

После запуска доступны:

```text
http://<central>:8090            # web-консоль управления
http://<central>:8080/health     # health API
http://<central>:8080/api/events # события collector
```

## Сенсор

1. Установи ОС на плату.
2. Включи SSH.
3. Убедись, что центральный узел видит IP платы.
4. Открой `http://<central>:8090`.
5. Настрой сенсор: IP, honeypot, сервисы внутри honeypot, настройки и маскировку.
6. В блоке `Установка/обновление по SSH` введи SSH host/login/password.
7. Нажми `Установить/обновить`.

Центр сам:

- генерирует `sensors/<sensor>/`;
- ставит Docker/Compose на плату;
- копирует `sensor/Dockerfile`, runtime-скрипты, Cowrie-конфигурацию и compose;
- запускает `docker compose up -d --build` на сенсоре.

## Генерация Для Отладки

```sh
scripts/generate_sensor.sh
```

Команда создает ignored-артефакты:

- `sensors/<sensor>/.env`;
- `sensors/<sensor>/docker-compose.yml`;
- `sensors/<sensor>/cowrie/etc/cowrie.cfg`;

Эти файлы не хранятся в git.

## Проверка

Центр:

```sh
curl http://127.0.0.1:8080/health
curl http://127.0.0.1:8080/api/sensors | python3 -m json.tool
```

Сенсор с отдельной машины:

```sh
printf 'admin\r\n' | nc -w 2 <sensor-ip> 2222
printf 'admin\r\n' | nc -w 2 <sensor-ip> 2223
```

События проверяются через API:

```text
http://<central>:8080/api/events
```
