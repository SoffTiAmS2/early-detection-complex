# Early Detection Complex

Распределенный комплекс раннего выявления подозрительной сетевой активности на
основе управляемых honeypot-сенсоров.

Главная документация проекта находится в одном файле:

```text
docs/system_guide_ru.md
```

Начинай с него. Там описаны архитектура, модель `DeviceMaskProfile`, запуск,
сборка Docker-образов сенсора, Ansible, диагностика, тесты и карта файлов.

## Быстрый запуск центра

```bash
cp config/site.example.json config/site.local.json
make up
curl -u centre:1 http://127.0.0.1:8080/health
```

Центр будет доступен на `http://127.0.0.1:8080`, Grafana - на
`http://127.0.0.1:3000`.
По умолчанию UI центра защищен Basic Auth `centre` / `1`; Grafana использует
`centre` / `centre123`.

Compose также поднимает микросервисы:

```text
reverse-proxy   8080
manager-api     internal:8080
agent-gateway   8081
log-receiver    8091
config-renderer 8092
log-normalizer  background worker
```

## Быстрый запуск контейнерного агента

На узле сенсора, где уже доступны Docker и заранее собранные honeypot-образы:

```bash
export EDC_CENTER_URL=http://<central-ip>:8080
export EDC_SENSOR_ID=banana-pi-pro-1
export EDC_IMAGE_POLICY=prebuilt_only
make sensor-up
```

`compose.sensor.yml` запускает только `sensor-agent`. Контейнер монтирует
`/var/run/docker.sock` и `/var/lib/edc-sensor`, поэтому агент управляет
honeypot-контейнерами хостового Docker и сохраняет runtime-конфиги на хосте.
Создание сенсора и статус ожидания первого sync доступны в UI центра:
`http://<central-ip>:8080/settings`.

## Установка сенсора на чистый узел

В UI центра открой `http://<central-ip>:8080/settings` и заполни блок
`Создать и установить сенсор`: `ID`, `Host`, `SSH user`, `SSH password / sudo`,
`Профиль`. Кнопка `Установить по SSH` сама:

- создаст сенсор в политике;
- подключится к узлу по SSH;
- установит Docker/Python через `apt`, `pacman` или `dnf`;
- скопирует минимальный bundle `compose.sensor.yml` + `sensor/`;
- запустит контейнерный `sensor-agent`;
- покажет статус установки и последние строки лога в UI.

Для полностью офлайн-образа сенсора заранее включи в образ Docker,
`docker compose plugin`, Python 3 и загрузи honeypot images
`edc/cowrie:local`, `edc/glutton:local`, `edc/honeypy:local`,
`edc/mailoney:local`, `edc/conpot:local`. Тогда оставляй
`EDC_IMAGE_POLICY=prebuilt_only`, и агент не будет пытаться собирать тяжелые
honeypot-образы на слабом железе.

## Быстрые проверки

```bash
make check
python3 tools/e2e_reconfigure_test.py
```

## Текущий honeypot-стек

```text
cowrie
conpot
mailoney
honeypy
glutton
```

Старый стек `opencanary/heralding/dionaea` не является активным направлением
проекта.

## Профили маскировки

Новая главная сущность проекта - профиль устройства, а не отдельный контейнер.
Каталог лежит в `catalog/device_mask_profiles.json`, UI доступен на
`/profiles`, Dockerfiles сенсора вынесены в `sensor/dockerfiles/`.

## Логи honeypot

Сырые строки логов сохраняются в `raw_honeypot_logs`, нормализованные события -
в `honeypot_events`. Для Grafana добавлен dashboard `EDC Honeypot Logs`.

## Что не коммитить

```text
artifacts/
var/
__pycache__/
*.pyc
config/site.local.json
ВКРТекст.md
```
