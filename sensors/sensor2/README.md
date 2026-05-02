# sensor2

## Назначение

Сенсор `sensor2` предназначен для роли `office` и использует профиль `cowrie`.

Профиль: SSH/Telnet brute-force profile.

## Сетевые параметры

- IP сенсора: `192.168.10.12`
- Центральный узел: `192.168.10.2:8080`
- Отправка событий: `http://192.168.10.2:8080/api/events`

## Маскировка

- Имя-легенда: `office-filesrv-01`
- ОС-легенда: `Debian GNU/Linux 13`
- Подразделение: `Office`
- Asset tag: `OFF-FS-01`

## Сервисы-приманки

- `ssh` on TCP `2222`: `ssh`
- `telnet` on TCP `2323`: `telnet`

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
