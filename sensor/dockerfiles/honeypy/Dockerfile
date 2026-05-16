ARG HONEYPY_BASE_IMAGE=python:2.7-slim-buster
FROM ${HONEYPY_BASE_IMAGE}

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Debian Buster уже в archive.debian.org.
RUN set -eux; \
    printf '%s\n' \
      'deb http://archive.debian.org/debian buster main' \
      'deb http://archive.debian.org/debian-security buster/updates main' \
      'deb http://archive.debian.org/debian buster-updates main' \
      > /etc/apt/sources.list; \
    apt-get -o Acquire::Check-Valid-Until=false update; \
    apt-get install -y --no-install-recommends \
      git \
      ca-certificates \
      build-essential \
      libffi-dev \
      libssl-dev; \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    "pip<21" \
    "setuptools<45" \
    "wheel<0.35"

WORKDIR /opt

RUN git clone --depth 1 https://github.com/foospidy/HoneyPy.git /opt/HoneyPy && \
    git clone --depth 1 https://github.com/foospidy/clilib.git /opt/clilib

WORKDIR /opt/clilib
RUN python setup.py install

WORKDIR /opt/HoneyPy

RUN pip install --no-cache-dir \
    "dnslib==0.9.7" \
    "requests==2.20.0" \
    "urllib3<1.25" \
    "certifi" \
    "zope.interface<5.0.0" \
    "Twisted==14.0.2" \
    "python_twitter==3.1" \
    "pika==0.10.0" \
    "hpfeeds3==0.9.8"

COPY etc/honeypy.cfg /opt/HoneyPy/etc/honeypy.cfg
COPY etc/services.cfg /opt/HoneyPy/etc/services.cfg

RUN mkdir -p /logs/internal && \
    chmod -R 777 /logs && \
    chmod +x /opt/HoneyPy/Honey.py && \
    chown -R 65534:65534 /opt/HoneyPy /logs

USER 65534:65534

WORKDIR /opt/HoneyPy

EXPOSE 10023/tcp 10080/tcp 10025/tcp 19200/tcp 10007/tcp 10008/tcp 12048/tcp

CMD ["python", "/opt/HoneyPy/Honey.py", "-d"]
