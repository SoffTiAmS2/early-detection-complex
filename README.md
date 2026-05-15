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

Центр будет доступен на `http://127.0.0.1:8080`.

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

## Что не коммитить

```text
artifacts/
var/
__pycache__/
*.pyc
config/site.local.json
ВКРТекст.md
```
