FROM python:3.12-slim

WORKDIR /app
COPY fake_service.py /app/fake_service.py

ENV HONEYPOT_LOG_PATH=/logs/events.jsonl
ENV FAKE_SERVICE_PORTS=2222,8081
EXPOSE 2222 8081

CMD ["python", "/app/fake_service.py"]

