# Web configurator

Web-конфигуратор находится в `manager/` и запускается без внешних зависимостей.

## Запуск

```sh
scripts/start_manager.sh
```

По умолчанию интерфейс доступен на:

```text
http://127.0.0.1:8090
```

## Что можно настроить

- лабораторную подсеть;
- шлюз;
- IP центрального узла;
- список сенсоров;
- профиль каждого сенсора;
- набор сервисов-приманок;
- параметры маскировки.

## API

- `GET /api/catalog` - список профилей и сервисов.
- `GET /api/project` - текущий `inventory/project.json`.
- `PUT /api/project` - сохранить конфигурацию.
- `POST /api/generate` - запустить `orchestrator/generate.py`.

## Как это связано с установкой

После сохранения и генерации web-интерфейс обновляет:

- `inventory/project.json`;
- `inventory/network.yml`;
- `inventory/sensors.yml`;
- `sensors/<sensor>/.env`;
- `sensors/<sensor>/docker-compose.yml`;
- `sensors/<sensor>/config/services.json`.

