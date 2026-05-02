# Deployment

Полный отчет по реализации и эксплуатации см. также:

- `docs/full_report.md`;
- `/home/shizik/Yandex.Disk/Document/Obsidian Vault/ВКР/Документация_early_detection_complex/10_полный_отчет_о_реализации.md`;
- `/home/shizik/Yandex.Disk/Document/Obsidian Vault/ВКР/Документация_early_detection_complex/11_инструкция_по_эксплуатации.md`.

## Требования

- Центральный узел: Debian/Armbian и Docker/Compose. `scripts/install_central.sh` ставит их сам.
- Сенсорная плата: установленная ОС, сеть и включенный SSH.
- Docker, Compose и конфигурацию на сенсор ставит центральная web-консоль через Ansible.

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

Web-режим работает внутри центрального Docker stack и доступен на `http://<central>:8090`.

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

Скрипт устанавливает Docker/Compose, включает сервис Docker и запускает `central-node/docker-compose.yml`.

После запуска доступны:

- `http://<central>:8090` - web-консоль управления и установки сенсоров;
- `http://<central>:8080/health`;
- `http://<central>:8080/api/events`;
- `http://<central>:8080/api/sensors`;
- `http://<central>:8080/dashboard`.

## Сенсор

1. Установи ОС на плату.
2. Включи SSH и убедись, что IP доступен с центрального узла.
3. Открой `http://<central>:8090`.
4. Добавь или выбери сенсор, укажи IP/профиль/сервисы/маскировку.
5. В блоке `Установка/обновление по SSH` введи SSH host, login и password.
6. Нажми `Установить/обновить`.

Центр сам сгенерирует конфигурацию, поставит Docker на сенсор, скопирует нужные файлы и запустит контейнеры.

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
