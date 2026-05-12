# Early Detection Complex / Комплекс Раннего Обнаружения

Распределённый комплекс раннего обнаружения подозрительной сетевой активности на основе honeypot.

## Что Сейчас Главное

Проект больше не строится вокруг MVP-веб-панели. Центр - это API/control-plane:

- хранит policy и raw events;
- принимает `POST /api/sensors/<id>/sync` от сенсоров;
- отдает Prometheus metrics на `/metrics`;
- визуализируется через Prometheus + Grafana;
- устанавливается и сопровождается через Ansible.

Сенсор запускает реальные honeypot-контейнеры через Docker Compose. Для Banana Pi Pro Cowrie собирается локально из `sensor/images/cowrie/Dockerfile` с фиксированными входами и выходами: `cowrie.cfg`, `userdb.txt`, `var/log/cowrie`, `tty`, `downloads`, `:9000/metrics`.

## Запуск Центра

Проще всего:

```sh
make up
```

Если `make` не установлен:

```sh
docker compose up -d --build
```

После запуска:

```text
API:        http://<ip-центра>:8080
Prometheus: http://<ip-центра>:9090
Grafana:    http://<ip-центра>:3000
```

Локально без Docker:

```sh
python3 -m center.main --host 0.0.0.0 --port 8080
```

Для первого знакомства смотри [docs/beginner_guide.md](docs/beginner_guide.md).

Рабочая политика центра хранится в `config/site.local.json`. Если файла нет, центр при первом запуске скопирует его из `config/site.example.json`.

## Что Нужно На Плате

Минимум:

```text
ОС Linux + сеть + SSH + пользователь с sudo или root
```

Поддерживается установка на Banana Pi Pro с Armbian. Docker и `edc-sensor.service` ставятся Ansible playbook-ом.

На 32-bit ARM Cowrie собирается локально. Остальные honeypot images запускаются через тот же Docker-runtime; если конкретный upstream image не поддерживает ARMv7, ошибка будет видна в status и Prometheus/Grafana.

## Установка Через Ansible

```sh
cd ansible
ansible-playbook playbooks/site.yml --ask-pass --ask-become-pass
```

Удаление сенсора с остановкой runtime, удалением файлов и очисткой policy:

```sh
cd ansible
ansible-playbook playbooks/remove_sensor.yml --limit banana-pi-pro-1 --ask-pass --ask-become-pass
```

## Структура

```text
center/     # отдельное Python-приложение центра
sensor/     # agent и Docker runtime, которые запускаются на плате
ansible/    # установка, классификация и удаление центра/сенсоров
observability/ # Prometheus rules и Grafana provisioning
catalog/    # описание поддерживаемых honeypot-модулей и их настроек
config/     # политика стенда: сенсоры, профили, порты, persona
scripts/    # локальные helper-скрипты
tools/      # проверки политики и e2e reconfigure-тест
docs/       # архитектура, карта файлов, стенд, roadmap
compose.yml # центр + Prometheus + Grafana
Makefile    # короткие команды запуска и проверки
pyproject.toml, requirements.txt # упаковка Python-проекта, зависимостей нет
```

Старые прототипы и сгенерированные runtime-файлы больше не хранятся в git.

## Honeypot Runtime / Запуск Honeypot

Сенсор не имитирует протоколы сам. Он запускает реальные upstream Docker images:

```text
Cowrie     local build from sensor/images/cowrie/Dockerfile
OpenCanary thinkst/opencanary:latest
Dionaea    dinotools/dionaea:latest
Conpot     honeynet/conpot:latest
Heralding  dtagdevsec/heralding:24.04.1
```

Sensor-agent удаляет старые контейнеры комплекса с label `edc.sensor_id=<sensor_id>`, применяет новую конфигурацию, читает `docker logs` и отправляет сырые события в центр.

## Проверки

```sh
make check
python3 tools/e2e_reconfigure_test.py
```
