ARG HONEYPOT_BASE_IMAGE=python:3.9-slim
FROM ${HONEYPOT_BASE_IMAGE}

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=300 \
    PIP_RETRIES=10 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential \
       cmake \
       ninja-build \
       libpq-dev \
       libssl-dev \
       libffi-dev \
       libzmq3-dev \
       ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --upgrade "pip<24.1" "setuptools<70" wheel scikit-build-core cython \
    && pip install --no-cache-dir --no-build-isolation --timeout 300 --retries 10 heralding \
    || pip install --no-cache-dir --no-build-isolation --timeout 300 --retries 10 heralding

CMD ["heralding", "--help"]
