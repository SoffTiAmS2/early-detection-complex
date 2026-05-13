#!/usr/bin/env bash
set -euo pipefail

SENSOR_ID="${1:-${EDC_SENSOR_ID:-}}"
if [[ -z "$SENSOR_ID" ]]; then
  echo "usage: $0 <sensor-id>"
  echo "or set EDC_SENSOR_ID env"
  exit 1
fi

echo "== host =="
hostname
uname -a
echo

echo "== service =="
if systemctl list-unit-files | grep -q '^edc-sensor.service'; then
  systemctl status edc-sensor.service --no-pager -l | sed -n '1,25p'
else
  echo "edc-sensor.service not installed"
fi
echo

echo "== docker =="
docker --version
docker compose version || true
echo

echo "== containers (label edc.sensor_id=$SENSOR_ID) =="
docker ps -a --filter "label=edc.sensor_id=$SENSOR_ID" --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
echo

echo "== recent logs per container (last 10 lines) =="
ids="$(docker ps -aq --filter "label=edc.sensor_id=$SENSOR_ID" || true)"
if [[ -z "$ids" ]]; then
  echo "no containers found"
else
  for id in $ids; do
    name="$(docker inspect --format '{{.Name}}' "$id" | sed 's#^/##')"
    echo "--- $name ---"
    docker logs --tail 10 "$id" 2>&1 || true
  done
fi
echo

echo "== listening ports =="
ss -lntp | sed -n '1,120p'
