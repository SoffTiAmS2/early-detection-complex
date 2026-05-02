FROM python:3.12-slim

WORKDIR /app
COPY server.py /app/server.py

ENV CENTRAL_BIND=0.0.0.0
ENV CENTRAL_PORT=8080
ENV EVENT_STORE=/data/events.jsonl

EXPOSE 8080
CMD ["python", "/app/server.py"]

