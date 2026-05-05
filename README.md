# Early Detection Complex

Новая ветка проекта строится как легкая deception-платформа для раннего обнаружения подозрительной сетевой активности.

Старый рабочий прототип с Cowrie, manager API, Ansible и web-архивом сохранен в `archive/prototype-v0/`. Он больше не считается основной архитектурой, но остается как источник проверенных кусков: сборка Cowrie на ARM, доставка событий, Ansible-деплой и generated-конфигурация.

## Новый Вектор

Берем архитектурные идеи из open-source deception-платформ:

- HoneySens: центр управляет сенсорами, сенсоры получают конфигурацию и обновления от сервера.
- T-Pot CE: большой каталог honeypot и sensor/hive-модель как референс, но без тяжелого ELK-комбайна в первом этапе.
- OpenCanary: легкий multi-protocol honeypot как первый кандидат после Cowrie.
- Cowrie: качественная SSH/Telnet deception.
- Honeytrap: модель listeners, services и event channels для внутреннего sensor runtime.

## Целевая Структура

```text
center/               # control-plane: API, registry, policies, events
sensor/               # appliance-agent: polling, module runtime, status, update/rollback
catalog/              # specs honeypot-модулей и профилей deception
config/               # пример политики стенда
docs/                 # новая архитектура и roadmap
archive/prototype-v0/ # старый рабочий прототип, сохранен без удаления
```

## Принцип

Сенсорная плата должна требовать минимум ручной работы:

```text
ОС + сеть + SSH + регистрация в центре
```

Дальше центр должен:

- зарегистрировать сенсор;
- выдать ему desired state;
- подготовить нужные honeypot-модули;
- управлять портами, профилем и deception-данными;
- получать события, status heartbeat и health;
- обновлять sensor runtime и honeypot-модули;
- откатывать неудачные обновления.

## Первый MVP Новой Архитектуры

1. Описать каталог модулей: Cowrie, OpenCanary, Heralding, Conpot, Dionaea.
2. Сделать единый sensor manifest: какие modules включены, какие ports слушают, куда слать события.
3. Сделать lightweight sensor-agent, который polling-ом забирает desired state с центра.
4. Поднять Cowrie как первый модуль.
5. Добавить OpenCanary как легкий multi-service модуль.
6. После этого возвращаться к UI, уже поверх нормальной модели управления.

## Проверка Новой Политики

Пока это не runtime, но уже есть проверяемая модель каталога и desired state:

```sh
tools/validate_policy.py
```

Валидатор проверяет, что `config/site.example.json` использует только существующие modules/services из `catalog/honeypots.json` и не содержит конфликтов host ports на одном сенсоре.

## MVP Control Loop

Уже есть минимальный живой цикл без Docker и UI:

```sh
scripts/run_mvp.sh
```

Что он показывает:

1. Запускает `center/server.py`.
2. `sensor/agent.py` забирает `GET /api/sensors/sensor1/desired-state`.
3. Агент строит локальный dry-run plan по Cowrie/OpenCanary.
4. Агент пишет `var/sensor/applied_state.json`.
5. Агент отправляет `sensor.status` в `POST /api/events`.
6. Центр показывает sensor summary через `GET /api/sensors`.

Ручной запуск:

```sh
python3 center/server.py --host 127.0.0.1 --port 8080
python3 sensor/agent.py --center http://127.0.0.1:8080 --sensor-id sensor1 --once
curl http://127.0.0.1:8080/api/sensors
```

Это пока dry-run, но это уже правильный каркас: центр хранит desired state, сенсор сам его забирает и докладывает результат.

## Где Старый Код

Проверенный прототип находится здесь:

```text
archive/prototype-v0/
```

Он нужен как reference implementation, но новый код должен расти в корневых `center/`, `sensor/`, `catalog/`, `config/` и `docs/`.
