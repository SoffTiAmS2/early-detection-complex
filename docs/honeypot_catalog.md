# Honeypot Catalog

Manager использует единый справочник `center/honeypots/catalog.py`. В выборе остаются только honeypot, которые реально генерируются и ставятся на сенсор.

## Cowrie

Основание: официальная документация Cowrie и локальная копия документации, использованная при настройке. Cowrie ориентирован на SSH/Telnet, fake filesystem, shell interaction, скачанные артефакты, backend `shell/proxy`, `listen_endpoints` и версию SSH-баннера.

В manager доступны:

- сервисы: `ssh`, `telnet`;
- host-port для каждого сервиса;
- настройки: `hostname`, `ssh_version`, `backend`, `auth_class`, `download_limit_size`, `sftp_enabled`.

## Важное Ограничение

OpenCanary, Conpot, Dionaea и Heralding не показываются в UI, пока для них не добавлены настоящий контейнер, генератор конфигурации и сбор логов. Это лучше, чем иметь красивый, но нерабочий выбор.
