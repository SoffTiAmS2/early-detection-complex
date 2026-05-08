# Sensor Appliance

Сенсор в новой архитектуре - это managed appliance, установленный на плату.

## Responsibilities

- enrollment в центре;
- polling desired state;
- установка/обновление honeypot-модулей;
- запуск реальных Docker honeypot-модулей;
- очистка старых контейнеров комплекса перед применением новой политики;
- сбор raw container logs и доставка их в центр;
- local health;
- normalized event pipeline;
- rollback при неудачном обновлении.

## Runtime Shape

```text
edc-sensor-agent
├─ control loop
├─ Docker Compose runtime
├─ raw log collectors
├─ local state
└─ updater
```

## Bootstrap

SSH используется только чтобы поставить agent первый раз:

```text
center -> ssh -> install sensor-agent -> sensor-agent talks to center
```

После bootstrap центр не должен вручную конфигурировать каждую мелочь на плате.
