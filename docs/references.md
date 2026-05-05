# Open-Source References

Эта архитектура проектируется не вокруг старого прототипа, а вокруг проверенных идей из open-source deception-платформ.

## HoneySens

Reference: `https://honeysens.org/docs/`

Что берем:

- центральный server как control-plane;
- сенсор как легкий managed node;
- регулярное получение конфигурации сенсором;
- удаленное обновление sensor software;
- registry honeypot-сервисов;
- модель early-warning sensor.

Что не копируем напрямую:

- внутреннюю реализацию без отдельного анализа лицензии, зависимостей и сложности.

## T-Pot CE

Reference: `https://github.com/telekom-security/tpotce`

Что берем:

- список honeypot-кандидатов;
- sensor/hive mental model;
- практику multi-honeypot deployment;
- идеи нормализации событий.

Что не берем в MVP:

- полный ELK stack;
- тяжелую all-in-one установку;
- требование больших ресурсов на каждой плате.

## OpenCanary

Reference: `https://github.com/thinkst/opencanary`

Что берем:

- легкий multi-protocol honeypot;
- раннее обнаружение в локальной сети;
- множество сервисов в одном модуле.

Роль в проекте: первый модуль после Cowrie.

## Cowrie

Reference: `https://github.com/cowrie/cowrie`

Что берем:

- качественный SSH/Telnet honeypot;
- fake shell;
- userdb;
- honeyfs;
- command/session/download events.

Роль в проекте: первый real module, потому что он уже проверен в `archive/prototype-v0/`.

## Honeytrap

Reference: `https://github.com/honeytrap/honeytrap`

Что берем:

- внутреннюю модель listeners, services и channels;
- модульность event pipeline;
- идею отделения сетевого listener от логики сервиса.

Роль в проекте: референс для будущего sensor-agent runtime.
