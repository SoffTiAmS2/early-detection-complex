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
curl http://127.0.0.1:8080/health
```

Центр будет доступен на `http://127.0.0.1:8080`, Grafana - на
`http://127.0.0.1:3000`.

Compose также поднимает микросервисы:

```text
reverse-proxy   8080
manager-api     internal:8080
agent-gateway   8081
log-receiver    8091
config-renderer 8092
log-normalizer  background worker
```

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
