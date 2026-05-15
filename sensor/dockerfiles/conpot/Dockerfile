ARG HONEYPOT_BASE_IMAGE=python:3.8-slim
FROM ${HONEYPOT_BASE_IMAGE}

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libxml2-dev \
    libxslt1-dev \
    libffi-dev \
    libssl-dev \
    libpcap-dev \
    libev-dev \
    zlib1g-dev \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    "pip<24.0" \
    "setuptools<69" \
    "wheel" \
    "Cython==0.29.37"

RUN pip install --no-cache-dir --no-build-isolation \
    "gevent==21.12.0" \
    "greenlet==1.1.3"

RUN echo "lxml<5.0" > /tmp/pip-constraints.txt

RUN pip install --no-cache-dir --no-build-isolation \
    -c /tmp/pip-constraints.txt \
    "pyasn1==0.4.8" \
    "pysmi==0.3.4" \
    "pysnmp==4.4.12" \
    conpot==0.6.0

RUN rm -f /tmp/pip-constraints.txt && \
    mkdir -p /var/log/conpot && chmod -R 777 /var/log/conpot

EXPOSE 5020 10200 8800 44818 47808/udp
CMD ["conpot", "--template", "default", "--config", "/etc/conpot/conpot.cfg", "--logfile", "/logs/conpot.log", "--temp_dir", "/tmp"]
