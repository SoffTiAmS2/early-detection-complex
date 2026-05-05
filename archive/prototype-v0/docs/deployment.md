# Deployment

## Требования

- Центральный узел: Debian/Armbian с доступом к интернету.
- Сенсорная плата: Debian/Armbian, сеть и включенный SSH.
- На сенсор заранее не нужно ставить Docker, Cowrie или копировать проект.

## Центральный Узел

Из корня проекта:

```sh
scripts/install_central.sh
```

Скрипт ставит Docker/Compose, включает Docker и запускает:

- `collector` на `8080`;
- API-manager на `8090`.

После запуска доступны:

```text
http://<central>:8090            # manager API
http://<central>:8080/health     # health API
http://<central>:8080/api/events # события collector
```

## Сенсор

1. Установи ОС на плату.
2. Включи SSH.
3. Убедись, что центральный узел видит IP платы.
4. Настрой сенсор в `config/project.json`: IP, honeypot, сервисы внутри honeypot, настройки и маскировку.
5. Запусти установку с центра:

```sh
EDC_CENTER_URL=http://127.0.0.1:8090 scripts/deploy_sensor.sh sensor1 <sensor-ip> root 22
```

Центр сам:

- генерирует `sensors/<sensor>/`;
- ставит Docker/Compose на плату;
- останавливает старый compose stack сенсора и удаляет orphan/leftover контейнеры этого EDC-сенсора;
- копирует `sensor/Dockerfile`, runtime-скрипты, Cowrie-конфигурацию и compose;
- запускает новый managed compose project `edc_<sensor>` через `docker compose up -d --build`.

Подробный установочный контракт honeypot описан в `docs/honeypot_installation.md`.

## Генерация Для Отладки

```sh
scripts/generate_sensor.sh
```

Команда создает ignored-артефакты:

- `sensors/<sensor>/.env`;
- `sensors/<sensor>/docker-compose.yml`;
- `sensors/<sensor>/cowrie/etc/cowrie.cfg`;

Эти файлы не хранятся в git.

## Проверка

Центр:

```sh
curl http://127.0.0.1:8080/health
curl http://127.0.0.1:8080/api/sensors | python3 -m json.tool
```

Сенсор с отдельной машины:

```sh
printf 'admin\r\n' | nc -w 2 <sensor-ip> 2222
printf 'admin\r\n' | nc -w 2 <sensor-ip> 2223
```

События проверяются через API:

```text
http://<central>:8080/api/events
```
