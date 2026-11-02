FROM python:3.12.12-slim-bookworm@sha256:593bd06efe90efa80dc4eee3948be7c0fde4134606dd40d8dd8dbcade98e669c

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /opt/proxy
COPY proxy.py ./proxy.py
USER 65534:65534
EXPOSE 3128
CMD ["python", "/opt/proxy/proxy.py"]
