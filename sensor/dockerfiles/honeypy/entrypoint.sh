#!/bin/sh
set -eu

mkdir -p /logs
cd /app

for candidate in /app/Honey.py /app/honey.py /app/honeypy.py /app/HoneyPy.py; do
  if [ -f "$candidate" ]; then
    exec python "$candidate" -c /etc/honeypy/config.yml
  fi
done

echo "honeypy entrypoint: upstream startup file not found" >&2
find /app -maxdepth 3 -type f | sort >&2
exit 127
