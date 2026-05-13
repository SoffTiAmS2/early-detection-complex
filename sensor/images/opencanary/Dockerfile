FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential \
       cargo \
       rustc \
       pkg-config \
       libssl-dev \
       libffi-dev \
       libpcap-dev \
       ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --upgrade pip "setuptools<81" wheel setuptools-rust \
    && pip install --no-cache-dir --no-build-isolation opencanary==0.9.7

CMD ["opencanaryd", "--dev", "--config=/root/.opencanary.conf"]
