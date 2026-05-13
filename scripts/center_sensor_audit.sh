#!/usr/bin/env bash
set -euo pipefail

CENTER_URL="${1:-${EDC_CENTER_URL:-http://127.0.0.1:8080}}"
echo "center: $CENTER_URL"

payload="$(curl -fsS "$CENTER_URL/api/overview")"
python3 - "$payload" <<'PY'
import json,sys
data=json.loads(sys.argv[1])
sensors=data.get("sensors",[])
print(f"sensors_total={len(sensors)} online={sum(1 for s in sensors if s.get('health')=='online')} stale={sum(1 for s in sensors if s.get('health')=='stale')}")
for s in sensors:
    sid=s.get("sensor_id")
    host=s.get("host","")
    health=s.get("health",s.get("status","unknown"))
    mods=",".join(f"{m.get('id')}:{m.get('status')}" for m in (s.get("modules") or []))
    print(f"{sid}\t{host}\t{health}\t{mods}")
PY
