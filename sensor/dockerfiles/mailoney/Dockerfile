ARG MAILONEY_BASE_IMAGE=python:3.11-slim
FROM ${MAILONEY_BASE_IMAGE}

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MAILONEY_HOST=0.0.0.0 \
    MAILONEY_PORT=2525 \
    MAILONEY_SERVER_NAME=mail.company.local \
    EDC_SENSOR_ID=banana-pi-mailoney \
    MAILONEY_LOG_DIR=/logs \
    MAILONEY_LOGIN_RESULT=success \
    MAILONEY_TIMEOUT=60 \
    MAILONEY_MAX_LINE_BYTES=8192 \
    MAILONEY_MAX_MESSAGE_BYTES=262144 \
    MAILONEY_PREVIEW_CHARS=2000

RUN mkdir -p /opt/mailoney /logs && chmod -R 777 /logs

WORKDIR /opt/mailoney

COPY mailoney_lite.py /opt/mailoney/mailoney_lite.py

RUN chmod +x /opt/mailoney/mailoney_lite.py && \
    python3 -m py_compile /opt/mailoney/mailoney_lite.py

USER 65534:65534

EXPOSE 2525/tcp

CMD ["python3", "/opt/mailoney/mailoney_lite.py"]
