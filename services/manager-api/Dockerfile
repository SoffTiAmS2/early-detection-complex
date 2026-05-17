FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "psycopg[binary]==3.2.12"

WORKDIR /app
COPY catalog ./catalog
COPY config ./config
COPY center ./center
COPY sensor ./sensor
COPY scripts ./scripts
COPY tools ./tools

EXPOSE 8080
CMD ["python3", "-m", "center.main", "--host", "0.0.0.0", "--port", "8080"]
