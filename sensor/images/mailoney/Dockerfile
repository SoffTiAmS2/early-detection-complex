ARG HONEYPOT_BASE_IMAGE=python:3.11-slim
FROM ${HONEYPOT_BASE_IMAGE}

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
RUN git clone --depth 1 https://github.com/awhitehatter/mailoney.git /app \
    && if [ -f requirements.txt ]; then pip install --no-cache-dir -r requirements.txt; fi

COPY entrypoint.sh /usr/local/bin/mailoney-entrypoint
RUN chmod +x /usr/local/bin/mailoney-entrypoint \
    && mkdir -p /logs

EXPOSE 2525
CMD ["mailoney-entrypoint"]
