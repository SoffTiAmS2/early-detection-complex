ARG COWRIE_BASE_IMAGE=arm32v7/alpine:3.19
ARG COWRIE_REF=v2.9.18
FROM ${COWRIE_BASE_IMAGE}
ARG COWRIE_REF=v2.9.18

USER root
RUN apk add --no-cache \
    bash \
    build-base \
    cargo \
    git \
    libffi-dev \
    openssl-dev \
    py3-pip \
    python3 \
    python3-dev \
    rust \
    && ln -sf python3 /usr/bin/python

RUN adduser -D -h /home/cowrie -s /bin/bash cowrie
USER cowrie
WORKDIR /home/cowrie

RUN git clone --depth 1 --branch "${COWRIE_REF}" https://github.com/cowrie/cowrie.git \
    && cd cowrie \
    && python3 -m venv cowrie-env \
    && . cowrie-env/bin/activate \
    && pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -e . \
    && cp etc/cowrie.cfg.dist etc/cowrie.cfg \
    && mkdir -p var/log/cowrie var/lib/cowrie/tty var/lib/cowrie/downloads var/lib/cowrie/data

EXPOSE 2222 2223 9000
CMD ["/home/cowrie/cowrie/bin/cowrie", "start", "-n"]
