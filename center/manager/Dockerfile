FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ansible openssh-client sshpass rsync \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY center/ansible /app/center/ansible
COPY center/manager /app/center/manager
COPY center/orchestrator /app/center/orchestrator
COPY config /app/config
COPY sensor/containers /app/sensor/containers

EXPOSE 8090
CMD ["python", "center/manager/backend/server.py", "--host", "0.0.0.0", "--port", "8090"]
