#!/usr/bin/env sh
set -eu

PYTHONPYCACHEPREFIX="${TMPDIR:-/tmp}/edc-pycache" python3 -m compileall center sensor tools services
python3 tools/validate_profiles.py
python3 tools/validate_policy.py
python3 tools/check_log_normalizer.py
if [ "${EDC_CHECK_LOCAL_POLICY:-0}" = "1" ] && [ -f config/site.local.json ]; then
  python3 tools/validate_policy.py --policy config/site.local.json
fi
docker compose config >/dev/null
