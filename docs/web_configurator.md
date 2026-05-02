# Web Console

Web-консоль запускается в составе центрального Docker stack.

```sh
scripts/install_central.sh
```

Адрес:

```text
http://<central-ip>:8090
```

## Возможности

- настройка подсети, шлюза и IP центрального узла;
- добавление и удаление сенсоров;
- выбор профиля и сервисов-приманок;
- настройка deception-маскировки;
- генерация конфигураций;
- установка или обновление сенсора по SSH через Ansible.

## API

- `GET /api/catalog` - профили и сервисы.
- `GET /api/project` - текущий `inventory/project.json`.
- `PUT /api/project` - сохранить конфигурацию.
- `POST /api/generate` - сгенерировать ignored-артефакты в `sensors/`.
- `POST /api/deploy-sensor` - сгенерировать конфигурацию и установить/обновить сенсор по SSH.

## Хранение Данных

Tracked source of truth:

```text
inventory/project.json
```

Generated ignored files:

```text
sensors/<sensor>/
inventory/network.yml
inventory/sensors.yml
```

SSH-пароль используется только во время текущего Ansible-запуска и не сохраняется в `inventory/project.json`.
