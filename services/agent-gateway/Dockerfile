FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV PYTHONPATH=/app
COPY services/agent-gateway ./services/agent-gateway

EXPOSE 8081
CMD ["python3", "/app/services/agent-gateway/app.py"]
