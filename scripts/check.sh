#!/usr/bin/env sh
set -eu

python3 -m compileall center sensor tools
python3 tools/validate_policy.py
if [ -f config/site.local.json ]; then
  python3 tools/validate_policy.py --policy config/site.local.json
fi
docker compose config >/dev/null
