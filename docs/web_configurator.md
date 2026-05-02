# Web configurator

Web-консоль находится в `manager/` и обычно запускается внутри центрального Docker stack.

## Запуск

```sh
scripts/install_central.sh
```

По умолчанию интерфейс доступен на:

```text
http://<central-ip>:8090
```

## Что можно настроить

- лабораторную подсеть;
- шлюз;
- IP центрального узла;
- список сенсоров;
- профиль каждого сенсора;
- набор сервисов-приманок;
- параметры маскировки.
- SSH host/login/password для установки или обновления сенсора.

## API

- `GET /api/catalog` - список профилей и сервисов.
- `GET /api/project` - текущий `inventory/project.json`.
- `PUT /api/project` - сохранить конфигурацию.
- `POST /api/generate` - запустить `orchestrator/generate.py`.
- `POST /api/deploy-sensor` - сгенерировать конфигурацию и установить/обновить сенсор по SSH через Ansible.

## Как это связано с установкой

После сохранения и генерации web-интерфейс обновляет:

- `inventory/project.json`;
- `inventory/network.yml`;
- `inventory/sensors.yml`;
- `sensors/<sensor>/.env`;
- `sensors/<sensor>/docker-compose.yml`;
- `sensors/<sensor>/config/services.json`.

После этого кнопка `Установить/обновить` запускает `ansible/deploy_sensor.yml`.
Пароль используется только для текущего запуска Ansible и не записывается в `inventory/project.json`.
