# Full Report And Usage Guide

Подробный русскоязычный отчет для ВКР вынесен в Obsidian Vault:

```text
/home/shizik/Yandex.Disk/Document/Obsidian Vault/ВКР/Документация_early_detection_complex/10_полный_отчет_о_реализации.md
/home/shizik/Yandex.Disk/Document/Obsidian Vault/ВКР/Документация_early_detection_complex/11_инструкция_по_эксплуатации.md
```

Краткий порядок запуска:

```sh
cd /home/shizik/Yandex.Disk/early-detection-complex
scripts/start_manager.sh
scripts/generate_sensor.sh
cd central-node
docker compose up -d --build
cd ../sensors/sensor1
docker compose up -d --build
```

Проверка:

```sh
curl http://127.0.0.1:8080/health
curl http://127.0.0.1:8080/api/sensors | python3 -m json.tool
printf 'test\r\n' | nc -w 2 127.0.0.1 2222
tail -n 20 sensors/sensor1/logs/events.jsonl
```

Dashboard:

```text
http://<central-node-ip>:8080/dashboard
```
