ARG COWRIE_BASE_IMAGE=arm32v7/debian:bookworm-slim
ARG COWRIE_REF=v2.6.1
FROM ${COWRIE_BASE_IMAGE}
ARG COWRIE_REF=v2.6.1

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        git \
        python3 \
        python3-attr \
        python3-automat \
        python3-bcrypt \
        python3-constantly \
        python3-cryptography \
        python3-hyperlink \
        python3-idna \
        python3-incremental \
        python3-packaging \
        python3-pip \
        python3-pyasn1 \
        python3-pyasn1-modules \
        python3-requests \
        python3-service-identity \
        python3-treq \
        python3-twisted \
        python3-urllib3 \
        python3-venv \
        python3-zope.interface \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf python3 /usr/bin/python

RUN useradd --create-home --home-dir /home/cowrie --shell /bin/bash cowrie
USER cowrie
WORKDIR /home/cowrie

RUN git clone --depth 1 --branch "${COWRIE_REF}" https://github.com/cowrie/cowrie.git \
    && cd cowrie \
    && python3 -m venv --system-site-packages cowrie-env \
    && . cowrie-env/bin/activate \
    && pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir --no-deps -e . tftpy==0.8.2 \
    && ln -sf /usr/bin/twistd3 cowrie-env/bin/twistd \
    && cp etc/cowrie.cfg.dist etc/cowrie.cfg \
    && mkdir -p var/log/cowrie var/lib/cowrie/tty var/lib/cowrie/downloads var/lib/cowrie/data

EXPOSE 2222 2223 9000
CMD ["/home/cowrie/cowrie/bin/cowrie", "start", "-n"]
