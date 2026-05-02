# sensor3

## Назначение

Сенсор `sensor3` предназначен для роли `ot-mining` и использует профиль `conpot`.

Профиль: OT/ICS mining operations profile.

## Сетевые параметры

- IP сенсора: `192.168.10.13`
- Центральный узел: `192.168.10.2:8080`
- Отправка событий: `http://192.168.10.2:8080/api/events`

## Маскировка

- Имя-легенда: `mine-telemetry-gw`
- ОС-легенда: `Embedded Linux`
- Подразделение: `Mining operations`
- Asset tag: `OT-TEL-01`

## Сервисы-приманки

- `http` on TCP `8081`: `http`
- `modbus` on TCP `1502`: `modbus`

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
