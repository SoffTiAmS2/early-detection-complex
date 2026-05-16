FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "psycopg[binary]==3.2.12"

WORKDIR /app
ENV PYTHONPATH=/app
COPY center ./center
COPY services/log-receiver ./services/log-receiver

EXPOSE 8091
CMD ["python3", "/app/services/log-receiver/app.py"]
