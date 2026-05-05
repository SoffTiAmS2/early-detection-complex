#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 3 ] || [ "$#" -gt 4 ]; then
  echo "Usage: EDC_CENTER_URL=http://<center>:8090 scripts/deploy_sensor.sh <sensor> <ssh_host> <ssh_user> [ssh_port]" >&2
  exit 2
fi

sensor="$1"
ssh_host="$2"
ssh_user="$3"
ssh_port="${4:-22}"
center_url="${EDC_CENTER_URL:-http://127.0.0.1:8090}"
center_url="${center_url%/}"

if [ -z "${EDC_SSH_PASSWORD:-}" ]; then
  printf "SSH password for %s@%s: " "$ssh_user" "$ssh_host" >&2
  stty -echo
  read -r EDC_SSH_PASSWORD
  stty echo
  printf "\n" >&2
fi

become_password="${EDC_BECOME_PASSWORD:-$EDC_SSH_PASSWORD}"

payload="$(
  SENSOR="$sensor" \
  SSH_HOST="$ssh_host" \
  SSH_USER="$ssh_user" \
  SSH_PORT="$ssh_port" \
  SSH_PASSWORD="$EDC_SSH_PASSWORD" \
  BECOME_PASSWORD="$become_password" \
  python3 - <<'PY'
import json
import os

print(json.dumps({
    "sensor": os.environ["SENSOR"],
    "ssh_host": os.environ["SSH_HOST"],
    "ssh_user": os.environ["SSH_USER"],
    "ssh_port": int(os.environ["SSH_PORT"]),
    "ssh_password": os.environ["SSH_PASSWORD"],
    "become_password": os.environ["BECOME_PASSWORD"],
}))
PY
)"

job_id="$(
  curl -fsS \
    -H "Content-Type: application/json" \
    -X POST \
    --data "$payload" \
    "$center_url/api/deploy-sensor" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["job"]["id"])'
)"

echo "Deploy job: $job_id"

while true; do
  job_json="$(curl -fsS "$center_url/api/jobs/$job_id")"
  JOB_JSON="$job_json" python3 - <<'PY'
import json
import os

job = json.loads(os.environ["JOB_JSON"])
status = job.get("status", "unknown")
progress = job.get("progress", 0)
step = job.get("step", "")
print(f"{progress:>3}% {status:<10} {step}")
output = job.get("output") or []
if output:
    print(output[-1])
PY
  status="$(JOB_JSON="$job_json" python3 -c 'import json,os; print(json.loads(os.environ["JOB_JSON"]).get("status", ""))')"
  case "$status" in
    succeeded)
      exit 0
      ;;
    failed|cancelled)
      exit 1
      ;;
  esac
  sleep 3
done
