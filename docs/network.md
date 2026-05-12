# Сетевая Схема

## Центр

Центр слушает:

```text
TCP 8080
```

Входящий трафик на центр:

- оператор/API-клиент -> `/api/overview`, `/api/policy`, `/api/sensors`, `/api/events`;
- Prometheus -> `GET /metrics`;
- сенсор -> `POST /api/sensors/<sensor_id>/sync`;
- сенсор -> `POST /api/events`.

Исходящий трафик из центра во время установки сенсора:

- центр -> сенсор `TCP 22` или другой настроенный SSH-порт;
- центр использует SSH/SCP, чтобы скопировать bundle сенсора и создать `edc-sensor.service`.

## Сенсор

Сенсор должен принимать SSH с центра во время установки:

```text
TCP 22
```

Для Banana Pi Pro / Armbian требования такие же:

```text
Armbian/Debian-based Linux + SSH + пользователь с sudo или root
```

Центр сам установит `python3`, Docker и Docker Compose. На 32-bit ARM тяжёлые модули, для которых нет подходящего image, будут пропущены runtime-ом с предупреждением в status.

После установки сенсор открывает honeypot-порты из политики центра. Политика-пример использует:

```text
2222  Cowrie SSH
2223  Cowrie Telnet
8081  OpenCanary HTTP
2121  OpenCanary FTP
6379  OpenCanary Redis
3306  OpenCanary MySQL
2122  Heralding FTP
8082  Heralding HTTP
1110  Heralding POP3
2525  Heralding SMTP
1502  Conpot Modbus
8800  Conpot HTTP
1445  Dionaea SMB
8083  Dionaea HTTP
2123  Dionaea FTP
```

Исходящий трафик с сенсора:

- сенсор -> центр `TCP 8080` для sync и отправки raw events;
- сенсор -> Docker registry при скачивании honeypot-образов.

## Авторизация

Административная авторизация необязательна и включается переменными окружения:

```sh
CENTER_AUTH_USER=admin
CENTER_AUTH_PASSWORD=change-me
```

или:

```sh
CENTER_AUTH_TOKEN=long-random-token
```

Когда авторизация включена, административные страницы и изменяющие API-запросы требуют логин/пароль или token. Сенсорные endpoints остаются открытыми, чтобы установленные агенты продолжали отправлять события.
