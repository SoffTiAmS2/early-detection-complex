FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ansible openssh-client sshpass rsync \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY ansible /app/ansible
COPY manager /app/manager
COPY orchestrator /app/orchestrator
COPY inventory /app/inventory
COPY containers /app/containers

EXPOSE 8090
CMD ["python", "manager/backend/server.py", "--host", "0.0.0.0", "--port", "8090"]
