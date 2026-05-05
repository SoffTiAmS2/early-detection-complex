# Honeypot Integration Plan

Цель: сенсор для пользователя должен оставаться одним управляемым сервисом `edc-sensor`. Внутри этого сервиса могут работать несколько honeypot-процессов, но manager должен управлять ими как единым профилем сенсора: выбрать приманки, сервисы, порты, легенду, применить конфиг, установить/обновить по SSH и получать события в одном формате.

## Правило Качества

Honeypot можно показывать в UI только после того, как для него есть:

- официальный или хорошо поддерживаемый способ установки;
- генератор конфигурации из `config/project.json`;
- mapping host-port -> internal-port;
- runtime supervisor entry внутри `edc-sensor`;
- parser/adapter логов в единый формат collector;
- smoke-test запуска;
- документация по настройкам, входам, выходам и ограничениям.

Пункт в интерфейсе без рабочего контейнера, конфига и логов считается не поддержкой, а шумом.

## Общая Архитектура `edc-sensor`

Нужный целевой вид:

```text
edc-sensor
├── supervisor
├── cowrie
├── opencanary
├── conpot
├── dionaea
├── heralding
├── log adapters
└── display/status agent
```

В Docker Compose на плате остается один service:

```yaml
services:
  edc-sensor:
    build:
      context: ../../sensor
    ports:
      - "<host-port>:<internal-port>"
    volumes:
      - ./config:/opt/edc/config:ro
      - ./logs:/opt/edc/logs
      - ./data:/opt/edc/data
```

Внутри контейнера supervisor читает generated config и запускает только выбранные honeypot-процессы. Так центр управляет одним сервисом, но мы не смешиваем разные honeypot в один неразборчивый процесс.

## Cowrie

Статус: частично реализован.

Назначение: SSH/Telnet deception, fake filesystem, shell interaction, загрузки файлов, JSON-события.

Документация: Cowrie описывает `etc/userdb.txt`, `honeyfs`, `createfs`, `fs.pickle`, `honeyfs/etc/issue.net`, JSON output и downloads.

Что уже есть:

- единый `edc-sensor` на базе `cowrie/cowrie:latest`;
- генерация `cowrie.cfg`;
- генерация `userdb.txt`;
- генерация `honeyfs`;
- сборка `fs.pickle` через `createfs` при старте;
- доставка `cowrie.json` в collector.

Что еще надо улучшить:

- расширить persona-пакеты: `web-server`, `file-server`, `vpn-gateway`, `linux-admin-host`;
- генерировать больше правдоподобных файлов: `/etc/os-release`, `/etc/ssh/sshd_config`, `/var/www`, `/opt`, `/srv`, `/home/<user>/.ssh`;
- согласовать `uname`, motd, issue, passwd и выбранную ОС;
- добавить настройку credential policy: allow-list, deny-list, weak-password profile;
- добавить smoke-test: SSH login -> команда -> событие в collector.

## OpenCanary

Статус: кандидат на следующий рабочий модуль.

Назначение: широкий набор low-interaction сервисов и login traps: FTP, HTTP, HTTPS, HTTP proxy, MySQL, MSSQL, Telnet, SSH, Redis, SNMP, SIP, VNC, TFTP, NTP, Git, tcpbanner.

Документация OpenCanary показывает:

- сервисы включаются ключами вида `<service>.enabled`;
- порты задаются ключами вида `<service>.port`;
- `opencanaryd --copyconfig` создает JSON-конфиг;
- logger поддерживает `StreamHandler`, `FileHandler`, syslog, JSON socket, webhook;
- секреты можно передавать через environment variables.

Как интегрировать:

- добавить OpenCanary в `sensor/Dockerfile` как установленный runtime-компонент;
- генерировать `/opt/edc/config/opencanary/opencanary.conf`;
- писать логи в `/opt/edc/logs/opencanary/opencanary.log`;
- сделать log adapter, который читает JSON/plain события OpenCanary и приводит их к collector event schema;
- включить в UI только сервисы, которые реально прошли smoke-test.

Минимальный первый профиль:

- `ftp`, `http`, `mysql`, `redis`, `telnet`, `tcpbanner`;
- настройки: node_id, banners, honeycreds, ports, ignorelist.

Осторожно:

- SMB и portscan требуют отдельной настройки host-системы и iptables/log watchers, поэтому их нельзя обещать как “просто работает” внутри контейнера.

## Conpot

Статус: отдельный ICS-модуль, не смешивать с обычными IT-сервисами.

Назначение: ICS/SCADA deception: Modbus, S7, SNMP, HTTP и device templates.

Документация Conpot показывает:

- базовый конфиг содержит секции `[modbus]`, `[snmp]`, `[http]`, `[sqlite]`, `[hpfriends]`;
- шаблоны определяют эмулируемое устройство и протоколы;
- Conpot поддерживает JSON logger и SQLite logger;
- Docker считается быстрым способом запуска без локального Python stack.

Как интегрировать:

- выделить профиль `ics-plc`;
- генерировать `/opt/edc/config/conpot/conpot.cfg`;
- генерировать или поставлять templates: `default`, `guardian_ast`, `ipmi`, `kamstrup`, `proxy`, `s7`;
- писать JSON logs в `/opt/edc/logs/conpot/conpot.json`;
- adapter должен сохранять protocol, session_id, src/dst, request/response.

Минимальный первый профиль:

- Modbus TCP `502`;
- S7comm `102`;
- HTTP management `80/8080`;
- SNMP `161/udp`.

Осторожно:

- ICS-легенда должна быть отдельной от Cowrie Linux-host легенды. Для Conpot нужны vendor, device model, firmware, serial, PLC rack/slot, registers.

## Dionaea

Статус: сильный, но тяжелый кандидат; нужен отдельный build proof.

Назначение: malware/network-service honeypot: SMB, HTTP, FTP, TFTP, MSSQL, MySQL, SIP, MQTT, MongoDB, Memcached, UPnP и другие сервисы.

Документация Dionaea показывает:

- есть Docker-раздел;
- конфиг, running, integration, service modules и logging/ihandler документированы отдельно;
- `log_json` и `log_sqlite` являются штатными logging integrations;
- сервисы включаются через конфигурацию Dionaea.

Как интегрировать:

- сначала собрать отдельную ветку образа `edc-sensor` с Dionaea-зависимостями;
- генерировать `/opt/edc/config/dionaea/dionaea.cfg`;
- включить `log_json`;
- писать `/opt/edc/logs/dionaea/dionaea.json`;
- adapter должен нормализовать incidents: connection, download, shellcode/profile, credentials where available.

Минимальный первый профиль:

- SMB `445`;
- HTTP `80`;
- FTP `21`;
- TFTP `69/udp`;
- MSSQL `1433`;
- MySQL `3306`.

Осторожно:

- Dionaea имеет больше native/system dependencies, чем Cowrie/OpenCanary. Его нельзя добавлять в основной образ до проверки сборки на целевых ARM/amd64 платах.

## Heralding

Статус: хороший credential-capture модуль, но fingerprint-risk выше, чем у Cowrie.

Назначение: сбор учетных данных на множестве протоколов: FTP, Telnet, SSH, HTTP/HTTPS, POP3/POP3S, IMAP/IMAPS, SMTP, VNC, PostgreSQL, SOCKS5.

По доступным материалам:

- конфигурация задается YAML-файлом `heralding.yml`;
- логирование может идти в JSON и CSV;
- типичные файлы логов: `log_session.json`, `log_auth.csv`, `log_session.csv`;
- сервисы активируются в конфиге.

Как интегрировать:

- добавить `heralding.yml` generator;
- писать JSON session log в `/opt/edc/logs/heralding/log_session.json`;
- CSV credentials читать только adapter-ом, не отправлять пароли в UI без явной маскировки;
- в UI показывать предупреждение: это credential trap, не полноценная shell emulation.

Минимальный первый профиль:

- HTTP/HTTPS login;
- FTP;
- Telnet;
- PostgreSQL;
- SMTP.

Осторожно:

- SSH в Heralding не должен конфликтовать с Cowrie. Если нужен SSH deception, приоритет у Cowrie.

## Приоритет Реализации

1. Cowrie persona hardening.
2. OpenCanary как второй модуль: быстрее всего даст много сервисов с нормальным конфигом.
3. Conpot для отдельного ICS-профиля.
4. Heralding для credential traps без shell.
5. Dionaea после отдельной проверки сборки и ресурсов на платах.

## Требования К Manager

UI должен показывать дерево:

```text
Сенсор
└── Honeypot
    ├── Сервисы
    │   ├── service enabled
    │   └── host port
    └── Настройки
        ├── persona
        ├── banners
        ├── credentials
        └── protocol-specific fields
```

Manager не должен давать выбрать два сервиса на один host-port. Если два honeypot умеют SSH, UI должен объяснить конфликт и выбрать один.

## Требования К Логам

Все adapters должны приводить события к одному виду:

```json
{
  "sensor": "sensor1",
  "honeypot": "cowrie",
  "service": "ssh",
  "event_type": "login_attempt",
  "src_ip": "192.0.2.10",
  "src_port": 51234,
  "dst_port": 2222,
  "username": "admin",
  "password": "***",
  "raw": {}
}
```

Пароли можно хранить в raw storage только если это явно включено в настройках проекта. В UI по умолчанию показывать masked value.

## Источники

- Cowrie documentation: https://docs.cowrie.org/
- OpenCanary configuration: https://www.opencanary.org/en/latest/starting/configuration.html
- Conpot documentation: https://conpot.readthedocs.io/
- Dionaea documentation: https://dionaea.readthedocs.io/
- Dionaea Docker image: https://hub.docker.com/r/dinotools/dionaea
- Conpot Docker image: https://hub.docker.com/r/honeynet/conpot
- Heralding Docker image in T-Pot ecosystem: https://hub.docker.com/r/dtagdevsec/heralding
