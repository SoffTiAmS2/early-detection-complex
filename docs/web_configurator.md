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
- древовидный выбор honeypot;
- выбор сервисов и настроек внутри каждого honeypot;
- настройка deception-маскировки;
- генерация конфигураций;
- установка или обновление сенсора по SSH через Ansible.

## API

- `GET /api/catalog` - honeypot, сервисы и поля настроек.
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

## Дерево Honeypot

Новая схема сенсора:

```json
{
  "name": "sensor1",
  "host": "192.168.0.128",
  "role": "dmz",
  "honeypots": [
    {
      "type": "cowrie",
      "enabled": true,
      "services": [
        {"name": "ssh", "enabled": true, "host_port": 2222},
        {"name": "telnet", "enabled": true, "host_port": 2223}
      ],
      "settings": {
        "hostname": "srv01",
        "ssh_version": "SSH-2.0-OpenSSH_8.4"
      }
    }
  ],
  "mask": {}
}
```

Поля `profile` и `services` пока сохраняются для совместимости со старыми generated-файлами, но основная настройка идет через `honeypots[]`.
