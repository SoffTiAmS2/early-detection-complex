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
- `GET /api/project` - текущий `config/project.json`.
- `PUT /api/project` - сохранить конфигурацию.
- `POST /api/generate` - сгенерировать ignored-артефакты в `sensors/`.
- `GET /api/center/status` - статус collector и сенсоров, которые уже присылают события.
- `POST /api/deploy-sensor` - запустить фоновую установку/обновление сенсора по SSH.
- `GET /api/jobs` - список последних задач установки.
- `GET /api/jobs/<id>` - статус, прогресс и вывод задачи.
- `POST /api/jobs/<id>/cancel` - отменить установку.

## Хранение Данных

Tracked source of truth:

```text
config/project.json
```

Generated ignored files:

```text
sensors/<sensor>/
```

SSH-пароль используется только во время текущего Ansible-запуска и не сохраняется в `config/project.json`.
