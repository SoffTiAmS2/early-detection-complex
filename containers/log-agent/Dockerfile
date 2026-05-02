FROM python:3.12-slim

WORKDIR /app
COPY log_agent.py /app/log_agent.py

ENV CENTRAL_URL=http://central-node:8080/api/events
ENV HONEYPOT_LOG_PATH=/logs/events.jsonl

CMD ["python", "/app/log_agent.py"]

