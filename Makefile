.PHONY: help up down logs check e2e clean

help:
	@printf '%s\n' \
		'Команды EDC:' \
		'  make up      - собрать и запустить центр в Docker' \
		'  make down    - остановить Docker-стек' \
		'  make logs    - смотреть логи контейнера центра' \
		'  make check   - выполнить быстрые локальные проверки' \
		'  make e2e     - проверить API и генерацию runtime' \
		'  make clean   - удалить локальные runtime-файлы и Python-кэш'

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker logs -f edc-center

check:
	sh scripts/check.sh

e2e:
	PYTHONPYCACHEPREFIX="$${TMPDIR:-/tmp}/edc-pycache" python3 tools/e2e_reconfigure_test.py

clean:
	find center sensor tools -type d -name '__pycache__' -prune -exec rm -rf {} +
	rm -rf var
