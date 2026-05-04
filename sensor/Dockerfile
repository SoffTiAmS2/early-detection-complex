FROM python:3.12-slim-bookworm

ENV COWRIE_HOME=/cowrie/cowrie-git
ENV COWRIE_VENV=/cowrie/cowrie-env
ENV PATH=/cowrie/cowrie-env/bin:/cowrie/cowrie-git/bin:$PATH

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        cargo \
        git \
        libffi-dev \
        libssl-dev \
        pkg-config \
        procps \
        python3-dev \
        rustc \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --home-dir /cowrie --shell /bin/bash cowrie \
    && mkdir -p /cowrie/cowrie-git /cowrie/cowrie-env /opt/edc/runtime \
    && chown -R cowrie:cowrie /cowrie /opt/edc

USER root
COPY runtime /opt/edc/runtime
RUN chmod +x /opt/edc/runtime/entrypoint.py

USER cowrie
WORKDIR /cowrie
RUN git clone --depth 1 https://github.com/cowrie/cowrie.git /cowrie/cowrie-git \
    && python -m venv /cowrie/cowrie-env \
    && /cowrie/cowrie-env/bin/pip install --no-cache-dir --upgrade pip setuptools wheel \
    && /cowrie/cowrie-env/bin/pip install --no-cache-dir -r /cowrie/cowrie-git/requirements.txt \
    && /cowrie/cowrie-env/bin/pip install --no-cache-dir --editable /cowrie/cowrie-git

WORKDIR /cowrie/cowrie-git
ENTRYPOINT ["python3", "/opt/edc/runtime/entrypoint.py"]
