ARG HONEYPOT_BASE_IMAGE=python:3.8-slim-buster
FROM ${HONEYPOT_BASE_IMAGE}

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONUNBUFFERED=1

RUN set -eux; \
    printf '%s\n' \
      'deb http://archive.debian.org/debian buster main' \
      'deb http://archive.debian.org/debian-security buster/updates main' \
      'deb http://archive.debian.org/debian buster-updates main' \
      > /etc/apt/sources.list; \
    apt-get -o Acquire::Check-Valid-Until=false update; \
    apt-get install -y --no-install-recommends \
      build-essential \
      libxml2-dev \
      libxslt1-dev \
      libffi-dev \
      libssl-dev \
      libpcap-dev \
      libev-dev \
      zlib1g-dev \
      libjpeg-dev \
      libgmp-dev \
      ca-certificates; \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    "pip<24.0" \
    "setuptools<69" \
    "wheel" \
    "Cython==0.29.37"

RUN pip install --no-cache-dir --no-build-isolation \
    "gevent==21.12.0" \
    "greenlet==1.1.3"

RUN cat > /tmp/pip-constraints.txt <<'EOF'
lxml<5.0

# Conpot 0.6.0 тянет pyghmi -> cryptography>=2.1.
# Без пина pip берёт cryptography 47.x, которому нужен maturin/Rust.
cryptography==3.3.2
cffi<1.16
pycparser<2.22

# Старые совместимые версии для Python 3.8 / Debian Buster / ARMv7.
requests<2.32
urllib3<2
charset-normalizer<4
idna<4
certifi<2025

beautifulsoup4<4.13
soupsieve<2.6
typing-extensions<4.13

pytest<8
tox<4
sphinx<6
jinja2<3.2
MarkupSafe<2.2

pyOpenSSL<21
service-identity<22
attrs<24
EOF

RUN pip install --no-cache-dir --no-build-isolation \
    -c /tmp/pip-constraints.txt \
    "pyasn1==0.4.8" \
    "pysmi==0.3.4" \
    "pysnmp==4.4.12" \
    conpot==0.6.0
    
RUN rm -f /tmp/pip-constraints.txt

# Banana Pi / ARMv7 fix:
# Conpot 0.6.0 импортирует IEC104 всегда, даже если он не нужен.
# На текущей связке Conpot + Scapy это ломает старт.
# Для industrial-controller отключаем IEC104-импорт в entrypoint.
RUN python - <<'PY'
from pathlib import Path

entry = Path("/usr/local/bin/conpot")
s = entry.read_text()
out = []

for line in s.splitlines():
    stripped = line.lstrip()
    if "IEC104Server" in line and not stripped.startswith("#"):
        out.append("# EDC disabled on ARMv7 industrial-controller: " + line)
    else:
        out.append(line)

entry.write_text("\n".join(out) + "\n")

frames = Path("/usr/local/lib/python3.8/site-packages/conpot/protocols/IEC104/frames.py")
if frames.exists():
    text = frames.read_text()
    text = text.replace("S/E", "SE")
    frames.write_text(text)
PY

RUN set -eux; \
    mkdir -p \
      /etc/conpot \
      /logs \
      /var/lib/conpot \
      /var/log/conpot \
      /tmp/conpot; \
    chmod -R 777 \
      /logs \
      /var/lib/conpot \
      /var/log/conpot \
      /tmp/conpot

COPY conpot.cfg /etc/conpot/conpot.cfg

RUN set -eux; \
    chmod 644 /etc/conpot/conpot.cfg; \
    python -m py_compile /usr/local/bin/conpot

EXPOSE 5020/tcp 10201/tcp 8800/tcp 16100/udp 44818/tcp 47808/udp 6230/udp 2121/tcp 6969/udp

ENV HOME=/tmp/conpot \
    TMPDIR=/tmp/conpot

# Conpot от root не стартует.
USER 65534:65534

CMD ["conpot", "--template", "default", "--config", "/etc/conpot/conpot.cfg", "--logfile", "/logs/conpot.log", "--temp_dir", "/tmp/conpot"]