# Prototype v0 Archive

Здесь сохранен старый рабочий прототип:

- central collector;
- API manager;
- Ansible deploy;
- generated `sensors/<name>/`;
- Cowrie ARM build;
- log-agent;
- display-agent;
- experimental sensor-node;
- archived web frontend.

Этот код можно использовать как reference implementation, но новая архитектура развивается в корневых `center/`, `sensor/`, `catalog/`, `config/` и `docs/`.

Причина архивации: прототип доказал, что Cowrie можно поставить и запустить на сенсоре, но архитектурно он слишком привязан к прямому Ansible-деплою и одному honeypot.
