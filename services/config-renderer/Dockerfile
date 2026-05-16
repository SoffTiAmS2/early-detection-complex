FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY catalog ./catalog
COPY center ./center
COPY services/config-renderer ./services/config-renderer

EXPOSE 8092
CMD ["python3", "/app/services/config-renderer/app.py"]
