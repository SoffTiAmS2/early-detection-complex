ARG HONEYPOT_BASE_IMAGE=python:3.11-slim
FROM ${HONEYPOT_BASE_IMAGE}

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
RUN git clone --depth 1 https://github.com/foospidy/HoneyPy.git /app \
    && if [ -f requirements.txt ]; then pip install --no-cache-dir -r requirements.txt || true; fi

COPY entrypoint.sh /usr/local/bin/honeypy-entrypoint
RUN chmod +x /usr/local/bin/honeypy-entrypoint \
    && mkdir -p /logs

EXPOSE 8082 3307 6380 2124 2324
CMD ["honeypy-entrypoint"]
