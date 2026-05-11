.PHONY: help up down logs check e2e

help:
	@printf '%s\n' \
		'Команды EDC:' \
		'  make up      - собрать и запустить центр в Docker' \
		'  make down    - остановить Docker-стек' \
		'  make logs    - смотреть логи контейнера центра' \
		'  make check   - выполнить быстрые локальные проверки' \
		'  make e2e     - проверить API и генерацию runtime'

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker logs -f edc-center

check:
	sh scripts/check.sh

e2e:
	python3 tools/e2e_reconfigure_test.py
