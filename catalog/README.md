# Module Catalog

`catalog/honeypots.json` - registry honeypot-модулей, которые реально заведены в текущей policy.

Модуль считается рабочим только если у него есть:

- реальная установка;
- config contract и `config_schema`;
- event adapter;
- health check;
- smoke test;
- список поддержанных архитектур;
- понятный resource class.

Пункт без этих вещей нельзя добавлять в UI как доступный honeypot. Upstream-кандидаты держим в roadmap/references, а не в рабочем каталоге.

## Статусы

- `prototype-v0-tested` - есть проверенный код из архивного прототипа.
- `planned-first-class` - выбран как ближайший полноценный upstream runner.
- `planned` / `planned-heavy` / `planned-after-arm-check` - реальный upstream проект, но интеграция еще не выполнена.
Текущий sensor-agent умеет запускать lightweight listeners по сервисам из policy. Это дает раннее обнаружение и проверяет модель управления, но не заменяет полноценную интеграцию upstream-проектов.

Сейчас в рабочем каталоге оставлены только модули, которые прописаны в `config/site.example.json`: Cowrie, OpenCanary, Heralding, Conpot и Dionaea.

`config_schema` описывает операторскую поверхность настройки: тип поля, группу, default, select-options и подсказку. Поля, которые не помещаются в удобную форму, должны попадать в `raw_*` advanced override, чтобы будущий real runner мог сгенерировать полноценный upstream config без потери настроек.
