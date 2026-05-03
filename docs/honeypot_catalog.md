# Honeypot Catalog

Manager использует единый справочник `center/honeypots/catalog.py`. Интерфейс больше не предлагает отдельно выбирать “порты”. Пользователь выбирает honeypot, затем сервисы и настройки внутри него. Порты остаются внутренней частью выбранного сервиса, чтобы не получить случайную несовместимую конфигурацию.

## OpenCanary

Основание: официальная документация OpenCanary описывает набор canary-сервисов и JSON-конфигурацию с `device.node_id`, `device.listen_addr`, `*.enabled`, `*.port`, `http.skin`, honey credentials и logger-настройками.

В manager доступны:

- сервисы: `ssh`, `telnet`, `ftp`, `http`, `https`, `mysql`, `mssql`, `smtp`, `snmp`, `sip`, `vnc`, `redis`;
- настройки: `node_id`, `listen_addr`, `honeycred_user`, `honeycred_password`, `http_skin`.

## Cowrie

Основание: локальная документация `docs-cowrie-org-en-latest.md`. Cowrie ориентирован на SSH/Telnet, fake filesystem, shell interaction, скачанные артефакты, backend `shell/proxy/backend_pool/llm`, `listen_endpoints` и версию SSH-баннера.

В manager доступны:

- сервисы: `ssh`, `telnet`;
- настройки: `hostname`, `kernel_version`, `ssh_version`, `backend`, `auth_class`, `download_limit_mb`, `sftp_enabled`.

## Heralding

Основание: документация PyPI проекта Heralding описывает credential-catching honeypot и поддерживаемые протоколы `ftp`, `telnet`, `ssh`, `http`, `https`, `pop3`, `imap`, `smtp`, `vnc`, `postgresql`, `socks5`.

В manager доступны:

- сервисы: `ftp`, `telnet`, `ssh`, `http`, `https`, `pop3`, `imap`, `smtp`, `vnc`, `postgresql`, `socks5`;
- настройки: `listen_addr`, `ssh_version`, `capture_passwords`, `json_sessions`.

## Conpot

Основание: официальная документация Conpot описывает ICS honeypot, default profile для Siemens S7-200 и поверхность `MODBUS`, `HTTP`, `SNMP`, `s7comm`.

В manager доступны:

- сервисы: `http`, `modbus`, `s7`, `snmp`;
- настройки: `template`, `device_name`, `vendor`, `strict_mode`.

## Dionaea

Основание: официальная документация Dionaea описывает protocol modules, HTTP/HTTPS, FTP, SMB и другие сервисы для low-interaction malware collection.

В manager доступны:

- сервисы: `http`, `https`, `ftp`, `mysql`, `mssql`, `smb`, `sip`;
- настройки: `download_dir`, `capture_binaries`, `listen_addr`, `tls_enabled`, `nfq_enabled`.

## Honeytrap

Honeytrap оставлен как generic low-interaction профиль для кастомных decoy-сервисов проекта.

В manager доступны:

- сервисы: `ssh`, `http`, `ftp`, `printer`, `redis`;
- настройки: `banner_profile`, `connection_timeout_sec`, `capture_payloads`.

## Важное Ограничение

Текущая runtime-реализация все еще использует встроенный `fake-services` контейнер. Новый каталог и схема уже описывают реальные honeypot-настройки, но они пока используются для генерации deception-баннеров и `services.json`. Это сделано намеренно: сначала приводим конфигурационную модель и интерфейс к правильной форме, затем можно подключать настоящие контейнеры Cowrie/OpenCanary/Conpot без новой переделки manager.
