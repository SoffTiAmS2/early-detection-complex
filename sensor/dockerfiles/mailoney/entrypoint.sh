#!/bin/sh
set -eu

mkdir -p /logs
cd /app

if [ -f /app/mailoney.py ]; then
  exec python /app/mailoney.py --config /etc/mailoney/mailoney.cfg
fi

if [ -f /app/Mailoney.py ]; then
  exec python /app/Mailoney.py --config /etc/mailoney/mailoney.cfg
fi

echo "mailoney entrypoint: upstream startup file not found" >&2
find /app -maxdepth 2 -type f | sort >&2
exit 127
