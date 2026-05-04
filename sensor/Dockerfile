FROM cowrie/cowrie:latest

USER root
COPY runtime /opt/edc/runtime
RUN chmod +x /opt/edc/runtime/entrypoint.py

USER cowrie
ENTRYPOINT ["python3", "/opt/edc/runtime/entrypoint.py"]
