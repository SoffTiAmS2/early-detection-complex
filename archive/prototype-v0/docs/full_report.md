# Full Report And Usage Guide

Подробный русскоязычный отчет для ВКР вынесен в Obsidian Vault:

```text
/home/shizik/Yandex.Disk/Document/Obsidian Vault/ВКР/Документация_early_detection_complex/10_полный_отчет_о_реализации.md
/home/shizik/Yandex.Disk/Document/Obsidian Vault/ВКР/Документация_early_detection_complex/11_инструкция_по_эксплуатации.md
```

Краткий порядок запуска:

```sh
cd /home/shizik/Yandex.Disk/early-detection-complex
scripts/install_central.sh
```

Проверка:

```sh
curl http://127.0.0.1:8080/health
curl http://127.0.0.1:8080/api/sensors | python3 -m json.tool
```

Dashboard:

```text
http://<central-ip>:8090
http://<central-ip>:8080/api/events
```
