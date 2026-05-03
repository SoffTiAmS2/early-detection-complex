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
http://<central>:8080/dashboard  # dashboard событий
http://<central>:8080/health     # health API
```

## Сенсор

1. Установи ОС на плату.
2. Включи SSH.
3. Убедись, что центральный узел видит IP платы.
4. Открой `http://<central>:8090`.
5. Настрой сенсор: IP, профиль, сервисы, маскировку.
6. В блоке `Установка/обновление по SSH` введи SSH host/login/password.
7. Нажми `Установить/обновить`.

Центр сам:

- генерирует `sensors/<sensor>/`;
- ставит Docker/Compose на плату;
- копирует контейнеры и конфигурацию;
- запускает `docker compose up -d --build` на сенсоре.

## Генерация Для Отладки

```sh
scripts/generate_sensor.sh
```

Команда создает ignored-артефакты:

- `sensors/<sensor>/.env`;
- `sensors/<sensor>/docker-compose.yml`;
- `sensors/<sensor>/config/services.json`;

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
printf 'GET /admin HTTP/1.0\r\n\r\n' | nc -w 2 <sensor-ip> 8081
```

События проверяются через dashboard или API:

```text
http://<central>:8080/dashboard
http://<central>:8080/api/events
```
