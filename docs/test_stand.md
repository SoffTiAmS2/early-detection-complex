# Test Stand

Практический стенд проекта:

```text
center  192.168.0.196  user: centre
sensor1 192.168.0.173  user: banana
```

Пароли и приватные SSH-ключи не хранятся в репозитории.

Текущие пароли стенда: `centre / 1` и `banana / 1`. Их нельзя сохранять в tracked-конфигурации проекта.

## Что Проверяет Текущий MVP

Текущая версия проверяет distributed control loop и реальные lightweight listeners:

1. Центр публикует каталог honeypot-модулей.
2. Центр хранит desired state сенсора.
3. Sensor-agent регистрируется через `POST /api/enroll`.
4. Sensor-agent забирает `GET /api/sensors/sensor1/desired-state`.
5. Sensor-agent поднимает TCP listeners для включенных модулей.
6. Любая попытка подключения к listener превращается в normalized event.
7. Sensor-agent отправляет `sensor.status` и suspicious events в `POST /api/events`.
8. Центр показывает состояние через `/api/overview` и `/api/sensors`.

Центр сохраняет события в SQLite `var/center/events.sqlite3`: нормализованные поля используются для фильтрации, а исходное событие сохраняется целиком в `raw_event`.

Это lightweight runtime, а не полноценные upstream-контейнеры Cowrie/OpenCanary/Conpot. Его задача - дать проверяемое раннее обнаружение и контракт событий до подключения тяжелых модулей.

## Запуск Центра

На центральной машине:

```sh
cd ~/edc-mvp
python3 center/server.py --host 0.0.0.0 --port 8080
```

Проверка:

```sh
open http://192.168.0.196:8080/
curl http://192.168.0.196:8080/health | python3 -m json.tool
curl http://192.168.0.196:8080/api/overview | python3 -m json.tool
curl http://192.168.0.196:8080/api/modules | python3 -m json.tool
curl http://192.168.0.196:8080/api/policy | python3 -m json.tool
```

Dashboard на `/` содержит две части:

- мониторинг: сенсоры, сервисы, severity/module/service counters, последние события;
- список реально прописанных honeypot-модулей с переходом на отдельную страницу настройки.

Страница отдельного honeypot:

```text
http://192.168.0.196:8080/honeypots/opencanary?sensor_id=sensor1
http://192.168.0.196:8080/honeypots/cowrie?sensor_id=sensor1
http://192.168.0.196:8080/honeypots/heralding?sensor_id=sensor1
http://192.168.0.196:8080/honeypots/conpot?sensor_id=sensor1
http://192.168.0.196:8080/honeypots/dionaea?sensor_id=sensor1
```

На этой странице можно включать/отключать конкретный honeypot, включать сервисы, менять host-порты и settings.
Settings строятся из `config_schema` в `catalog/honeypots.json`, поэтому Cowrie уже содержит fake filesystem (`filesystem`/fs.pickle), `honeyfs`, `txtcmds`, `userdb`, auth, downloads, tty logs, shell persona, SSH banner и proxy backend, а не только пару поверхностных полей.

Добавить еще один сенсор в policy можно API-запросом. Desired state будет скопирован с `sensor1`, после чего новый агент сможет стартовать со своим `--sensor-id`:

```sh
curl -X POST http://192.168.0.196:8080/api/sensors \
  -H 'Content-Type: application/json' \
  -d '{"id":"sensor2","host":"192.168.0.177","architecture":"x86_64","clone_from":"sensor1"}' | python3 -m json.tool
```

После изменения политики через dashboard sensor-agent сам заберет новую версию desired state на следующем polling loop. В текущем запуске на стенде интервал обычно `10s`.

Если нужно принудительно перезапустить агент вручную:

```sh
ssh banana@192.168.0.173
cd ~/edc-mvp
kill $(cat var/sensor.pid) 2>/dev/null || true
nohup python3 sensor/agent.py --center http://192.168.0.196:8080 --sensor-id sensor1 --serve --interval 10 > var/sensor/agent.log 2>&1 &
echo $! > var/sensor.pid
```

## Запуск Sensor-Agent

На sensor1:

```sh
cd ~/edc-mvp
python3 sensor/agent.py --center http://192.168.0.196:8080 --sensor-id sensor1 --serve
cat var/sensor/applied_state.json | python3 -m json.tool
```

После этого на любой машине:

```sh
curl http://192.168.0.196:8080/api/sensors | python3 -m json.tool
curl 'http://192.168.0.196:8080/api/events?limit=10' | python3 -m json.tool
```

Ожидаемый смысл результата:

- `sensor1.status = online`;
- `sensor1.applied_version` равен текущей версии policy;
- `agent_mode = listener-runtime`;
- активны listeners для Cowrie, OpenCanary, Heralding, Conpot и Dionaea;
- в events есть `sensor.enroll`, `sensor.runtime.started`, `sensor.status` и события подключений.

## Проверка Менеджера Политики

Выключить OpenCanary целиком через API центра:

```sh
curl -X PATCH http://192.168.0.196:8080/api/sensors/sensor1/modules/opencanary \
  -H 'Content-Type: application/json' \
  -d '{"enabled": false}' | python3 -m json.tool
```

Через несколько секунд порт OpenCanary HTTP должен закрыться:

```sh
timeout 2 bash -c '</dev/tcp/192.168.0.173/8081' && echo open || echo closed
```

Включить обратно:

```sh
curl -X PATCH http://192.168.0.196:8080/api/sensors/sensor1/modules/opencanary \
  -H 'Content-Type: application/json' \
  -d '{"enabled": true}' | python3 -m json.tool
```

Порт должен снова открыться, а `applied_version` в `/api/sensors` должен догнать версию policy.

## Быстрая Проверка Детекта

С любой машины в сети:

```sh
curl -i http://192.168.0.173:8081/
curl -i http://192.168.0.173:8082/
printf 'USER admin\r\nPASS admin\r\n' | nc -w 2 192.168.0.173 2121
printf 'USER backup\r\nPASS backup123\r\n' | nc -w 2 192.168.0.173 2223
printf '*1\r\n$4\r\nPING\r\n' | nc -w 2 192.168.0.173 6379
```

Если `nc` не установлен, можно проверить TCP из bash:

```sh
timeout 2 bash -c '</dev/tcp/192.168.0.173/2222' && echo open
timeout 2 bash -c '</dev/tcp/192.168.0.173/8081' && echo open
```

После проверок:

```sh
curl 'http://192.168.0.196:8080/api/events?limit=20' | python3 -m json.tool
curl http://192.168.0.196:8080/api/overview | python3 -m json.tool
```

Фильтры событий:

```sh
curl 'http://192.168.0.196:8080/api/events?suspicious=1&severity=high&limit=20' | python3 -m json.tool
curl 'http://192.168.0.196:8080/api/events?suspicious=1&module=opencanary&limit=20' | python3 -m json.tool
curl 'http://192.168.0.196:8080/api/events?suspicious=1&service=http&limit=20' | python3 -m json.tool
```

В `/api/overview` должны увеличиться:

- `suspicious_event_count_window`;
- `severity_counts`;
- `recent_suspicious_events`.
