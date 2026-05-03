FROM python:3.12-slim

WORKDIR /app
COPY display_agent.py /app/display_agent.py

ENV SENSOR_NAME=sensor-unknown
ENV SENSOR_PROFILE=cowrie
ENV CENTRAL_HEALTH_URL=http://central-node:8080/health

CMD ["python", "/app/display_agent.py"]
