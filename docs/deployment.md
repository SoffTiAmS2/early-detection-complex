# Deployment

Полный отчет по реализации и эксплуатации см. также:

- `docs/full_report.md`;
- `/home/shizik/Yandex.Disk/Document/Obsidian Vault/ВКР/Документация_early_detection_complex/10_полный_отчет_о_реализации.md`;
- `/home/shizik/Yandex.Disk/Document/Obsidian Vault/ВКР/Документация_early_detection_complex/11_инструкция_по_эксплуатации.md`.

## Требования

- Armbian/Debian 13 на Banana Pi Pro.
- `python3`.
- `docker.io`.
- `docker-compose-plugin`.
- `i2c-tools`, если используется LCD 16x2.

## Генерация конфигураций

Интерактивный режим:

```sh
scripts/configure.sh
```

Он позволяет задать:

- IP центрального узла;
- IP каждого сенсора;
- honeypot/deception-профиль;
- набор сервисов-приманок;
- параметры маскировки.

Web-режим:

```sh
scripts/start_manager.sh
```

Адрес по умолчанию:

```text
http://127.0.0.1:8090
```

Повторная генерация без вопросов:

```sh
scripts/generate_sensor.sh
```

Команда запускает `orchestrator/generate.py` и создает для каждого сенсора:

- `.env`;
- `docker-compose.yml`;
- `README.md`.

## Центральный узел

```sh
scripts/install_central.sh
```

Скрипт устанавливает Docker, включает сервис и запускает `central-node/docker-compose.yml`.

После запуска доступны:

- `http://<central>:8080/health`;
- `http://<central>:8080/api/events`;
- `http://<central>:8080/api/sensors`;
- `http://<central>:8080/dashboard`.

## Сенсор

```sh
scripts/install_sensor.sh sensor1
scripts/start_sensor.sh sensor1
```

`install_sensor.sh` готовит плату, а `start_sensor.sh` запускает контейнеры выбранного сенсора.

## Проверка

```sh
scripts/health_check.sh sensor1
```

Проверяется Docker, связь с центральным узлом, наличие I2C и состояние контейнеров.

## Чистая система

На центральном узле:

```sh
scripts/bootstrap_clean.sh central
```

На сенсорной плате:

```sh
scripts/bootstrap_clean.sh sensor sensor1
```
