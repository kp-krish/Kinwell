# HeatCheck voice server (Twilio Media Streams <-> Amazon Nova 2 Sonic) for ECS Fargate.
FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY voice/requirements.txt voice/requirements.txt
RUN pip install -r voice/requirements.txt
COPY voice/ voice/
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8080/health')" || exit 1
CMD ["uvicorn", "voice.app:app", "--host", "0.0.0.0", "--port", "8080", "--ws-ping-interval", "20"]
