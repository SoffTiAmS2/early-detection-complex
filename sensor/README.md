# Sensor Appliance

Сенсор в новой архитектуре - это managed appliance, установленный на плату.

## Responsibilities

- enrollment в центре;
- polling desired state;
- установка/обновление honeypot-модулей;
- запуск module runner;
- local health;
- normalized event pipeline;
- rollback при неудачном обновлении.

## Runtime Shape

```text
edc-sensor-agent
├─ control loop
├─ module runner
├─ event adapters
├─ local state
└─ updater
```

## Bootstrap

SSH используется только чтобы поставить agent первый раз:

```text
center -> ssh -> install sensor-agent -> sensor-agent talks to center
```

После bootstrap центр не должен вручную конфигурировать каждую мелочь на плате.
