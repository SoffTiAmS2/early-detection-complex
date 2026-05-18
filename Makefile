.PHONY: help up down logs sensor-up sensor-down sensor-logs check e2e clean

help:
	@printf '%s\n' \
		'Команды EDC:' \
		'  make up      - собрать и запустить центр в Docker' \
		'  make down    - остановить Docker-стек' \
		'  make logs    - смотреть логи контейнера центра' \
		'  make sensor-up   - запустить sensor-agent в контейнере' \
		'  make sensor-down - остановить контейнерный sensor-agent' \
		'  make check   - выполнить быстрые локальные проверки' \
		'  make e2e     - проверить API и генерацию runtime' \
		'  make clean   - удалить локальные runtime-файлы и Python-кэш'

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f manager-api reverse-proxy

sensor-up:
	docker compose -f compose.sensor.yml up -d --build

sensor-down:
	docker compose -f compose.sensor.yml down

sensor-logs:
	docker compose -f compose.sensor.yml logs -f sensor-agent

check:
	sh scripts/check.sh

e2e:
	PYTHONPYCACHEPREFIX="$${TMPDIR:-/tmp}/edc-pycache" python3 tools/e2e_reconfigure_test.py

clean:
	find center sensor tools -type d -name '__pycache__' -prune -exec rm -rf {} +
	rm -rf var
