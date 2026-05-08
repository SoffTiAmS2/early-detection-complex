.PHONY: help up down logs check e2e

help:
	@printf '%s\n' \
		'EDC commands:' \
		'  make up      - build and start the center in Docker' \
		'  make down    - stop the Docker stack' \
		'  make logs    - follow center container logs' \
		'  make check   - run fast local checks' \
		'  make e2e     - run API/runtime materialization test'

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker logs -f edc-center

check:
	python3 -m compileall center sensor tools
	python3 tools/validate_policy.py
	docker compose config >/dev/null

e2e:
	python3 tools/e2e_reconfigure_test.py
