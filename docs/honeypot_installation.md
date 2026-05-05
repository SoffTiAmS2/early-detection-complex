# Установка Honeypot На Сенсор

Этот документ фиксирует рабочий путь без web-интерфейса. Центр управляет сенсорной платой по SSH: генерирует конфигурацию, ставит зависимости, очищает старые EDC-контейнеры и запускает новый managed compose project.

## Что Нужно На Плате

- Debian/Armbian или совместимая ОС.
- Сеть между центром и платой.
- SSH-доступ по паролю.
- Пользователь `root` или пользователь с `sudo`.

Docker, Compose, Cowrie и файлы проекта на плату заранее ставить не нужно.

## Команда Установки

Из корня проекта на центральном узле:

```sh
EDC_CENTER_URL=http://127.0.0.1:8090 scripts/deploy_sensor.sh sensor1 192.168.0.128 root 22
```

Скрипт попросит SSH password, отправит задачу в manager API и будет показывать:

- процент выполнения;
- текущий шаг Ansible;
- последнюю строку вывода;
- итог `succeeded`, `failed` или `cancelled`.

Пароль можно передать через переменную окружения, чтобы запускать автоматизированно:

```sh
EDC_CENTER_URL=http://192.168.0.27:8090 \
EDC_SSH_PASSWORD='Lolipop12' \
scripts/deploy_sensor.sh sensor1 192.168.0.128 root
```

## Что Делает Центр

1. Читает `config/project.json`.
2. Валидирует имя сенсора, honeypot, сервисы, порты и настройки.
3. Генерирует ignored-директорию `sensors/<sensor>/`.
4. Создает временный Ansible inventory только на время job.
5. Подключается к сенсору по SSH.
6. Ставит системные пакеты:
   - `docker.io`;
   - `docker-cli`;
   - `docker-compose-plugin` или legacy `docker-compose`;
   - `python3`;
   - `rsync`;
   - `curl`.
7. Включает и запускает Docker service.
8. Останавливает предыдущий EDC compose stack сенсора.
9. Удаляет leftover-контейнеры с compose labels `sensor` и `edc_<sensor>`.
10. Удаляет старые generated-файлы этого сенсора.
11. Копирует runtime-исходники `sensor/`.
12. Синхронизирует generated-файлы `sensors/<sensor>/` через `rsync`.
13. Запускает:

```sh
COMPOSE_PROJECT_NAME=edc_<sensor> docker compose up -d --build
```

Если на плате есть только legacy compose, используется `docker-compose`.

## Что Сейчас Реально Ставится

Сейчас production-путь включает один проверенный honeypot: Cowrie.

Cowrie запускается внутри единого образа `edc-sensor`. Образ собирается на самой плате из `sensor/Dockerfile`, чтобы не зависеть от внешнего amd64-only Docker image и работать на ARM.

Внутри образа:

- ставится Python runtime;
- скачивается Cowrie source checkout;
- создается venv;
- ставятся зависимости Cowrie;
- выполняется editable install, чтобы появились console scripts;
- стартует `twistd -n cowrie`;
- параллельно стартуют `sensor_node.py`, `log_agent.py` и `display_agent.py`.

## EDC Sensor Node

На сенсор ставится не просто Cowrie, а управляемый узел `edc-sensor`.

Внутри одного контейнера работают:

- `entrypoint.py` - supervisor процесса внутри контейнера;
- Cowrie - SSH/Telnet honeypot;
- `sensor_node.py` - status/control слой сенсора;
- `log_agent.py` - доставка событий honeypot в центр;
- `display_agent.py` - локальный статус для консоли или будущего дисплея.

`sensor_node.py` делает базовые функции комплекса раннего обнаружения:

- отправляет `sensor.status` в collector;
- пишет локальный state в `state/sensor_status.json`;
- передает версию сенсорного runtime;
- сообщает список активных honeypot, сервисов и портов;
- наблюдает `/proc/net/tcp` и `/proc/net/tcp6`;
- отправляет `sensor.connection_seen`, когда видит подключение к managed honeypot-порту.

Это дает ранний сигнал еще до глубоких событий Cowrie. Cowrie потом добавляет детальные события: успешный логин, неуспешный логин, команды, загрузки и закрытие сессии.

## Cowrie Конфигурация

Генератор создает:

```text
sensors/<sensor>/.env
sensors/<sensor>/docker-compose.yml
sensors/<sensor>/cowrie/etc/cowrie.cfg
sensors/<sensor>/cowrie/etc/userdb.txt
sensors/<sensor>/cowrie/honeyfs/
sensors/<sensor>/cowrie/downloads/
sensors/<sensor>/config/sensor_node.json
sensors/<sensor>/state/
sensors/<sensor>/logs/
```

Ключевые настройки:

- SSH слушает внутри контейнера `tcp/2222`.
- Telnet слушает внутри контейнера `tcp/2223`.
- Внешние host-порты берутся из `config/project.json`.
- `userdb.txt` задает фейковые учетные данные.
- `honeyfs/` задает фейковую файловую систему: `/etc/hostname`, `/etc/passwd`, `/etc/group`, `/etc/motd`, `/srv/backups`, home-директорию пользователя и следы истории.
- JSON-события пишутся в `var/log/cowrie/cowrie.json`.
- `log_agent.py` читает этот JSONL-файл и отправляет события в collector.
- `sensor_node.py` отправляет status и ранние сетевые события в тот же collector.

## Проверка После Установки

На центре:

```sh
curl http://127.0.0.1:8080/health
curl 'http://127.0.0.1:8080/api/events?limit=20' | python3 -m json.tool
```

На любой машине в сети:

```sh
ssh -p 2222 backup@<sensor-ip>
telnet <sensor-ip> 2223
```

На сенсоре:

```sh
docker ps --filter 'label=com.docker.compose.project=edc_sensor1'
docker logs edc_sensor1-edc-sensor-1 --tail 100
```

## Контракт Для Следующих Honeypot

Новые honeypot добавляются только если для них есть реальная установка, конфиг и smoke test. Нельзя добавлять пункт в каталог только ради UI.

Для каждого honeypot нужен одинаковый контракт:

- recipe сборки или установки внутри `sensor/Dockerfile`;
- template конфигурации в `center/orchestrator/generate.py`;
- volume mounts в generated `docker-compose.yml`;
- host-port mapping;
- путь к JSON/текстовым логам;
- adapter в `log_agent.py`, если формат не Cowrie JSONL;
- smoke test: порт открыт, login/interaction порождает событие, событие дошло в collector.

Порядок подключения:

1. Cowrie: SSH/Telnet deception, уже рабочий путь.
2. OpenCanary: легкие TCP/HTTP/FTP/SMB-приманки, после проверки конфигурации и логов.
3. Heralding: credential harvesting для нескольких протоколов, после проверки формата событий.
4. Conpot: ICS/SCADA deception, только после отдельной проверки шаблонов и ARM-сборки.
5. Dionaea: malware/service honeypot, только после проверки нативных зависимостей и размера образа.
