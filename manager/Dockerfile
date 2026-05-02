FROM python:3.12-slim

WORKDIR /app
COPY manager /app/manager
COPY orchestrator /app/orchestrator
COPY inventory /app/inventory

EXPOSE 8090
CMD ["python", "manager/backend/server.py", "--host", "0.0.0.0", "--port", "8090"]
