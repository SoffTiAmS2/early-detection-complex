# План проверки реальных Docker honeypot-модулей

Этот файл нужен для долгой проверки сборки и запуска без участия ассистента.
Заглушки в Docker-runtime не используются: контейнеры должны запускать реальные
upstream honeypot-проекты из `sensor/images/*/Dockerfile`.

## 1. Сборка ARMv7 bundle

На машине, где доступен Docker Buildx:

```bash
scripts/prebuild_armv7_bundle.sh 2>&1 | tee artifacts/build-armv7-$(date +%F-%H%M%S).log
```

После сборки должен появиться архив:

```bash
ls -lh artifacts/edc-armv7-images-*.tar.gz
```

Если сборка падает, сохрани и пришли:

- полный `artifacts/build-armv7-*.log`;
- имя модуля, на котором упала сборка;
- последние 80-120 строк ошибки.

## 2. Загрузка образов на сенсор

На Banana Pi Pro или другом ARMv7-сенсоре:

```bash
docker load -i artifacts/edc-armv7-images-YYYY-MM-DD-HHMMSS.tar.gz
docker image ls | grep '^edc/'
```

Ожидаемые образы:

```text
edc/cowrie:local
edc/conpot:local
edc/mailoney:local
edc/honeypy:local
edc/glutton:local
```

Пришли вывод:

```bash
docker image ls --format 'table {{.Repository}}\t{{.Tag}}\t{{.Size}}' | grep '^edc/'
```

## 3. Запуск сенсора в Docker-runtime

Проверь, что в рабочей политике для сенсора указан Docker-runtime:

```json
"runtime_mode": "docker"
```

Перезапусти сервис агента:

```bash
sudo systemctl restart edc-sensor
sleep 20
sudo systemctl status edc-sensor --no-pager
journalctl -u edc-sensor -n 120 --no-pager
```

Пришли:

- вывод `systemctl status edc-sensor --no-pager`;
- последние 120 строк `journalctl -u edc-sensor -n 120 --no-pager`.

## 4. Проверка контейнеров

На сенсоре:

```bash
docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}' | grep edc
```

Для каждого контейнера, который не в состоянии `Up`, пришли:

```bash
docker logs --tail 120 <container_name>
docker inspect <container_name> --format '{{json .State}}'
```

## 5. Проверка слушающих портов

На сенсоре:

```bash
ss -lntup | egrep '2222|2223|15020|10102|47808|8800|2525|8082|3307|6380|2124|2324|2375|1883|6443|3389|5900|5060'
```

Если порт не слушается, пришли:

- `docker ps -a` по контейнеру модуля;
- `docker logs --tail 120` по контейнеру модуля;
- последние строки `journalctl -u edc-sensor`.

## 6. Probe-тесты

С машины в той же сети:

```bash
nc -vz <sensor_ip> 2222
nc -vz <sensor_ip> 2223
curl -v --max-time 5 http://<sensor_ip>:8800/
printf 'HELO test.local\r\n' | nc -w 5 <sensor_ip> 2525
curl -v --max-time 5 http://<sensor_ip>:8082/
printf 'INFO\r\n' | nc -w 5 <sensor_ip> 6380
```

После probe-тестов на центре:

```bash
curl -sS 'http://127.0.0.1:8080/api/events?limit=30' | python3 -m json.tool
```

Пришли JSON последних событий или файл с ним:

```bash
curl -sS 'http://127.0.0.1:8080/api/events?limit=100' > artifacts/events-after-docker-runtime.json
```

## 7. Что нужно прислать мне

Минимальный набор для анализа:

```text
artifacts/build-armv7-*.log
docker image ls по edc/*
docker ps -a по edc-контейнерам
journalctl -u edc-sensor -n 120 --no-pager
docker logs --tail 120 для упавших контейнеров
artifacts/events-after-docker-runtime.json
```

Если какой-то модуль собирается, но не стартует, этого достаточно, чтобы
исправлять уже конкретный Dockerfile или команду запуска, а не гадать.
