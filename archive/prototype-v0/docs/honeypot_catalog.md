# Honeypot Catalog

Manager использует единый справочник `center/honeypots/catalog.py`. В выборе остаются только honeypot, которые реально генерируются и ставятся на сенсор.

## Cowrie

Основание: официальная документация Cowrie и локальная копия документации, использованная при настройке. Cowrie ориентирован на SSH/Telnet, fake filesystem, shell interaction, скачанные артефакты, backend `shell/proxy`, `listen_endpoints` и версию SSH-баннера.

В manager доступны:

- сервисы: `ssh`, `telnet`;
- host-port для каждого сервиса;
- настройки сети и поведения: `hostname`, `ssh_version`, `backend`, `auth_class`, `download_limit_size`, `sftp_enabled`;
- настройки deception-персоны: `login_user`, `login_password`, `shell_user`, `shell_uid`, `shell_gid`, `kernel_version`.

Генератор создает для Cowrie не только `cowrie.cfg`, но и рабочую легенду:

- `cowrie/etc/userdb.txt` - фейковая база учетных данных, через которую Cowrie решает, кого пустить внутрь;
- `cowrie/honeyfs/etc/hostname`, `issue.net`, `motd`, `passwd`, `group` - видимая системная маска;
- `cowrie/honeyfs/home/<user>/...` и `cowrie/honeyfs/srv/backups/...` - приманочные файлы;
- `cowrie/downloads` - место для файлов, загруженных атакующим.

При старте единый контейнер `edc-sensor` запускает `createfs` и собирает `fs.pickle` из `honeyfs`, после чего Cowrie использует этот filesystem в `[shell]`. Сам образ собирает Cowrie из исходников, поэтому подходит для ARM-плат, где официальный `cowrie/cowrie` image может не иметь нужного manifest. Это ближе к нормальной deception-модели: порт, баннер, логин, shell и файлы соответствуют одной легенде.

## Важное Ограничение

OpenCanary, Conpot, Dionaea и Heralding не показываются в UI, пока для них не добавлены настоящий runtime в `edc-sensor`, генератор конфигурации, mapping портов, parser логов и smoke-test. Детальный план подключения лежит в `docs/honeypot_integration_plan.md`.
