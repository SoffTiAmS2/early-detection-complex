# Early Detection Complex: единая книга проекта

Документ описывает проект целиком: назначение, архитектуру, запуск, сборку
honeypot-контейнеров, работу центра, работу сенсора, Ansible, диагностику и
рекомендации по чистке репозитория.

`ВКРТекст.md` этим документом не заменяется и не редактируется. Это
инженерная документация для разработки, тестирования и сопровождения кода.

## 1. Коротко о проекте

Early Detection Complex, или EDC, - распределенный комплекс раннего выявления
подозрительной сетевой активности. Он состоит из центрального узла и одного
или нескольких сенсоров.

Центр хранит политику, принимает события, показывает состояние сенсоров и
предоставляет API. Сенсор получает от центра desired-state, запускает реальные
honeypot-контейнеры и отправляет события назад в центр.

Проект не является SIEM, IPS или полноценной системой реагирования. Его задача
- дать ранний сигнал: если кто-то подключился к ложному сервису, это уже
событие для анализа.

## 2. Текущий стек

Основной стек модулей:

| Модуль | Назначение | Тип запуска |
|---|---|---|
| Cowrie | SSH/Telnet honeypot | локальная Docker-сборка |
| Conpot | ICS/SCADA honeypot | локальная Docker-сборка |
| Mailoney | SMTP honeypot | локальная Docker-сборка |
| HoneyPy | набор простых honeypot-сервисов | локальная Docker-сборка |
| Glutton | мультисервисный honeypot | локальная Docker-сборка |

Старые модули `opencanary`, `heralding`, `dionaea` выведены из активного
стека. Их не надо возвращать в рабочую политику, если цель - развивать новый
стек `cowrie/conpot/mailoney/honeypy/glutton`.

## 3. Главная идея архитектуры

```text
администратор
    |
    v
center:8080
    | хранит policy и события
    | отдает desired-state
    v
sensor-agent
    | генерирует docker-compose.yml
    | запускает контейнеры honeypot
    | читает логи модулей
    v
реальные honeypot-контейнеры
    ^
    |
источник сетевого probe/сканирования
```

Центр не открывает honeypot-порты. Порты открываются только на сенсоре.

Сенсор не должен сам решать, какие сервисы запускать. Он берет это из
desired-state, который центр формирует из `config/site.local.json` и
`catalog/honeypots.json`.

## 4. Основные каталоги

| Путь | Назначение |
|---|---|
| `center/` | HTTP API, веб-страницы, policy, события |
| `sensor/` | sensor-agent, Docker-runtime, native-runtime |
| `sensor/images/` | Dockerfiles реальных honeypot-модулей |
| `catalog/honeypots.json` | каталог поддерживаемых модулей и сервисов |
| `config/site.example.json` | пример рабочей политики |
| `config/site.local.json` | локальная рабочая политика стенда, не хранится в git |
| `ansible/` | установка центра и сенсоров на удаленные Linux-узлы |
| `scripts/` | вспомогательные команды проверки, сборки и диагностики |
| `tools/` | проверки политики и e2e smoke-тест |
| `docs/system_guide_ru.md` | главный документ проекта |
| `artifacts/` | тяжелые сборочные архивы, не коммитить |
| `var/` | локальные базы и runtime state, не коммитить |

## 5. Центр

Центр - это Python HTTP-приложение. Точка входа:

```text
center/main.py
center/app.py
center/api/handler.py
```

Основные маршруты:

| Маршрут | Назначение |
|---|---|
| `GET /health` | проверка статуса центра и policy |
| `GET /settings` | страница настройки центра и сенсоров |
| `GET /mask` | страница настройки легенды honeypot |
| `GET /db` | страница просмотра и очистки событий |
| `GET /api/policy` | получить текущую policy |
| `PUT /api/policy` | заменить policy |
| `GET /api/sensors` | получить состояние сенсоров |
| `POST /api/sensors` | добавить сенсор |
| `DELETE /api/sensors/<id>` | удалить сенсор из policy |
| `POST /api/sensors/<id>/sync` | sync от sensor-agent |
| `POST /api/events` | прием событий от runtime |
| `GET /api/events` | выборка событий |

Центр пишет события в PostgreSQL, если задан `CENTER_DB_DSN`. Если PostgreSQL
не включен, используется SQLite fallback.

Docker Compose по умолчанию запускает:

```text
edc-center
edc-postgres
```

## 6. Хранение данных

В PostgreSQL и SQLite используется одна логическая таблица `events`.

Основные поля события:

| Поле | Смысл |
|---|---|
| `received_at` | время приема центром |
| `timestamp` | время события на стороне сенсора, если есть |
| `event_type` | тип события |
| `sensor_id` | идентификатор сенсора |
| `module` | honeypot-модуль |
| `service` | сервис внутри модуля |
| `severity` | важность события |
| `src_ip` | источник подключения |
| `src_port` | порт источника |
| `dst_port` | порт назначения на сенсоре |
| `raw_sample` | короткий фрагмент события |
| `raw_event` | исходный JSON события |

Центр не обязан понимать все форматы логов каждого honeypot. Runtime сохраняет
исходное событие в `raw_event`, а нормализованные поля используются для
фильтров и интерфейса.

## 7. Policy и catalog

`catalog/honeypots.json` отвечает на вопрос: какие модули и сервисы вообще
поддерживаются проектом.

`config/site.local.json` отвечает на вопрос: какие сенсоры и сервисы включены
на конкретном стенде.

Правильный порядок:

```bash
cp config/site.example.json config/site.local.json
python3 tools/validate_policy.py --policy config/site.local.json
```

Если `config/site.local.json` принадлежит другому пользователю:

```bash
sudo chown "$USER":users config/site.local.json
```

Для текущего нового стека в policy должны быть модули:

```text
cowrie
conpot
mailoney
honeypy
glutton
```

## 8. Сенсор

Сенсор запускает `sensor/agent.py`.

Основной цикл:

1. Отправить sync в центр.
2. Получить desired-state.
3. Выбрать runtime.
4. Запустить runtime.
5. Периодически отправлять status.
6. Читать события runtime и отправлять их в центр.
7. При изменении desired-state перезапустить runtime.

Команда ручного запуска:

```bash
python3 sensor/agent.py \
  --center http://<center-ip>:8080 \
  --sensor-id banana-pi-pro-1 \
  --state-dir var/sensor \
  --serve \
  --interval 20
```

Systemd-сервис на сенсоре обычно запускает ту же команду.

## 9. Docker-runtime

Docker-runtime находится в:

```text
sensor/runtime.py
sensor/runtime_configs.py
sensor/runtime_helpers.py
sensor/runtime_status.py
```

Он делает следующее:

1. Проверяет наличие Docker и Docker Compose.
2. Создает runtime-каталог.
3. Копирует build context из `sensor/images/<module>/`.
4. Генерирует конфиги модулей.
5. Генерирует `docker-compose.yml`.
6. Удаляет старые контейнеры с label `edc.sensor_id=<sensor_id>`.
7. Запускает контейнеры.
8. Читает файлы логов модулей.
9. Отправляет события в центр.

Важно: Docker-runtime не должен имитировать сервисы своим Python-кодом. Он
должен запускать реальные honeypot-контейнеры.

## 10. Native-runtime

`sensor/native_runtime.py` - облегченный режим для ARMv7 или узлов без
рабочих Docker-образов.

Native-runtime полезен как запасной лабораторный режим, но основной
демонстрационный путь проекта сейчас - Docker-runtime с реальными
honeypot-контейнерами.

В policy режим выбирается так:

```json
"runtime_mode": "docker"
```

или:

```json
"runtime_mode": "native"
```

## 11. Ansible

Ansible в этом проекте - не отдельная бизнес-логика, а способ установки.

Он нужен, чтобы:

- установить Docker и зависимости;
- клонировать проект на центр и сенсоры;
- записать systemd unit `edc-sensor.service`;
- запустить agent на сенсоре;
- удалить сенсор при выводе из эксплуатации.

Главная команда:

```bash
cd ansible
ansible-playbook playbooks/site.yml --ask-pass --ask-become-pass
```

Если не хочешь использовать Ansible, можно запускать центр через Docker Compose
и sensor-agent вручную. Ansible не обязателен для понимания архитектуры.

## 12. Запуск центра

```bash
make up
```

Проверка:

```bash
curl http://127.0.0.1:8080/health
docker compose ps
docker compose logs -f center
```

Остановка:

```bash
make down
```

## 13. Сборка ARMv7 Docker bundle

Скрипт:

```bash
scripts/prebuild_armv7_bundle.sh 2>&1 | tee artifacts/build-armv7-$(date +%F-%H%M%S).log
```

Результат:

```text
artifacts/edc-armv7-images-YYYY-MM-DD-HHMMSS.tar.gz
```

Ожидаемые образы:

```text
edc/cowrie:local
edc/conpot:local
edc/mailoney:local
edc/honeypy:local
edc/glutton:local
```

Загрузка на сенсор:

```bash
docker load -i artifacts/edc-armv7-images-YYYY-MM-DD-HHMMSS.tar.gz
docker image ls --format 'table {{.Repository}}\t{{.Tag}}\t{{.Size}}' | grep '^edc/'
```

## 14. Проверка Docker-runtime

На сенсоре:

```bash
sudo systemctl restart edc-sensor
sleep 20
sudo systemctl status edc-sensor --no-pager
journalctl -u edc-sensor -n 120 --no-pager
```

Проверка контейнеров:

```bash
docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}' | grep edc
```

Проверка портов:

```bash
ss -lntup | egrep '2222|2223|15020|10102|47808|8800|2525|8082|3307|6380|2124|2324|2375|1883|6443|3389|5900|5060'
```

Probe-тесты:

```bash
nc -vz <sensor-ip> 2222
nc -vz <sensor-ip> 2223
curl -v --max-time 5 http://<sensor-ip>:8800/
printf 'HELO test.local\r\n' | nc -w 5 <sensor-ip> 2525
curl -v --max-time 5 http://<sensor-ip>:8082/
printf 'INFO\r\n' | nc -w 5 <sensor-ip> 6380
```

Проверка событий на центре:

```bash
curl -sS 'http://127.0.0.1:8080/api/events?limit=100' > artifacts/events-after-docker-runtime.json
```

## 15. Что присылать для анализа ошибок

Если сборка или запуск падает, нужен не пересказ, а артефакты:

```text
artifacts/build-armv7-*.log
docker image ls по edc/*
docker ps -a по edc-контейнерам
journalctl -u edc-sensor -n 120 --no-pager
docker logs --tail 120 для упавших контейнеров
artifacts/events-after-docker-runtime.json
```

Этого достаточно, чтобы исправлять конкретный Dockerfile, command, volume или
парсер логов.

## 16. Быстрые проверки разработчика

```bash
make check
python3 tools/e2e_reconfigure_test.py
```

Что проверяет `make check`:

- синтаксис Python;
- валидность `config/site.example.json`;
- валидность `compose.yml`.

Локальная policy конкретного стенда проверяется отдельно:

```bash
EDC_CHECK_LOCAL_POLICY=1 make check
```

Так сделано специально: `config/site.local.json` может принадлежать другому
пользователю, содержать временную лабораторную конфигурацию или старый стенд.
Качество репозитория проверяется по `config/site.example.json`.

Что проверяет e2e:

- запуск центра на свободном порту;
- sync сенсора;
- изменение policy через API;
- генерацию Docker Compose для реальных модулей.

## 17. Диагностика типовых проблем

| Симптом | Где смотреть | Что вероятно |
|---|---|---|
| `/health` возвращает `invalid_policy` | `config/site.local.json`, `tools/validate_policy.py` | policy не совпадает с catalog |
| Сенсор не появляется в центре | `journalctl -u edc-sensor` | неверный center URL, sensor_id не зарегистрирован |
| Контейнер не стартует | `docker ps -a`, `docker logs` | ошибка Dockerfile, command или volume |
| Порт не слушается | `ss -lntup`, `docker ps` | модуль упал или порт занят |
| Событие не появилось | логи модуля и `/api/events` | runtime не прочитал log file или модуль не пишет лог |
| ARMv7 образ не собирается | `artifacts/build-armv7-*.log` | upstream dependency не поддерживает ARMv7 |

## 18. Карта важных файлов кода

| Файл | Зачем нужен |
|---|---|
| `center/api/handler.py` | маршруты HTTP API и веб-страниц |
| `center/core/policy.py` | валидация policy, desired-state, изменение модулей |
| `center/core/profiles.py` | готовые профили сенсоров |
| `center/core/sensor_sync.py` | обработка sync от sensor-agent |
| `center/persistence/store.py` | подключение PostgreSQL/SQLite и миграции |
| `center/persistence/events.py` | запись, чтение, фильтрация и очистка событий |
| `sensor/agent.py` | основной цикл sensor-agent |
| `sensor/runtime.py` | Docker-runtime |
| `sensor/runtime_configs.py` | генерация конфигов модулей |
| `sensor/runtime_helpers.py` | справочники образов и helpers |
| `sensor/runtime_status.py` | чтение состояния Docker-контейнеров |
| `sensor/native_runtime.py` | запасной native-runtime |
| `scripts/prebuild_armv7_bundle.sh` | сборка ARMv7 bundle |
| `tools/e2e_reconfigure_test.py` | smoke-тест центра и runtime |

## 19. Что нельзя коммитить

Не коммитить:

```text
artifacts/
var/
__pycache__/
*.pyc
config/site.local.json
config/site.local.json.bak-*
ВКРТекст.md
```

Причины:

- `artifacts/` содержит тяжелые tar.gz образы;
- `var/` содержит runtime state и базы;
- `__pycache__/` и `*.pyc` генерируются Python;
- `site.local.json` является рабочей политикой конкретного стенда;
- `ВКРТекст.md` - отдельный текст ВКР, его нельзя менять в рамках рефакторинга.

## 20. Кандидаты на удаление после проверки

Пока я не удаляю эти файлы автоматически, потому что часть может быть нужна
для истории или защиты. Но для чистого продукта их стоит убрать или заменить
ссылкой на этот документ.

| Файл или каталог | Почему можно удалить |
|---|---|
| `docs/architecture.md` | устаревшее описание старого стека, дублирует эту книгу |
| `docs/beginner_guide.md` | частично дублирует запуск и структуру |
| `docs/file_map.md` | дублирует карту файлов из раздела 18 |
| `docs/network.md` | содержит устаревшие упоминания `/metrics` |
| `docs/roadmap.md` | полезно только как черновик планов |
| `docs/test_stand.md` | содержит старые `opencanary/dionaea/heralding` |
| `catalog/README.md` | короткий README, его смысл покрыт разделами 7 и 18 |
| `center/README.md` | дублирует описание центра из этой книги |
| `sensor/README.md` | после проверки стоит заменить ссылкой на эту книгу |
| `config/site.local.json.bak-old-stack` | локальный backup старой policy, не нужен в git |
| `center/1.txt`, `sensor/1.txt` | временные файлы, уже игнорируются |
| `artifacts/*.tar.gz` | тяжелые сборочные артефакты, хранить вне git |
| `__pycache__/`, `*.pyc` | генерируемый Python-кэш |

Рекомендуемый порядок удаления:

1. Сначала провести сборку и тесты нового Docker-стека.
2. Сохранить нужные результаты тестов вне git.
3. Удалить устаревшие docs или заменить их короткими ссылками на
   `docs/system_guide_ru.md`.
4. Проверить `make check`.
5. Сделать отдельный commit `Clean obsolete docs and local artifacts`.

## 21. Минимальный сценарий для понимания проекта

1. Прочитать `config/site.example.json`.
2. Прочитать `catalog/honeypots.json`.
3. Запустить центр: `make up`.
4. Проверить: `curl http://127.0.0.1:8080/health`.
5. Собрать ARMv7 bundle или локальные образы.
6. Запустить `sensor/agent.py --serve`.
7. Проверить `docker ps`.
8. Сделать probe на honeypot-порт.
9. Посмотреть `/api/events`.

Если эти девять шагов понятны, понятна вся система.
