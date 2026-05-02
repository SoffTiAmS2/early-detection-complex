# sensor1

## Назначение

Сенсор `sensor1` предназначен для роли `dmz` и использует профиль `opencanary`.

Профиль: multi-service decoy profile.

## Сетевые параметры

- IP сенсора: `192.168.10.11`
- Центральный узел: `192.168.10.2:8080`
- Отправка событий: `http://192.168.10.2:8080/api/events`

## Маскировка

- Имя-легенда: `dmz-backup-gw`
- ОС-легенда: `Debian GNU/Linux 13`
- Подразделение: `DMZ`
- Asset tag: `DMZ-BAK-01`

## Сервисы-приманки

- `ssh` on TCP `2222`: `ssh`
- `http` on TCP `8081`: `http`
- `ftp` on TCP `2121`: `ftp`
- `smtp` on TCP `2525`: `smtp`

## Компоненты

- `fake-services` - встроенный рабочий deception-слой с выбранными портами и баннерами.
- `log-agent` - читает локальный файл событий и отправляет их на центральный узел.
- `display-agent` - показывает статус сенсора и связь с центральным узлом.

## Запуск

```sh
docker compose up -d --build
docker compose ps
```

## Проверка

```sh
docker compose logs --tail=50
```
