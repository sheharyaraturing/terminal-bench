FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /root

RUN mkdir -p /logs/agent /logs/verifier /logs/artifacts /root /skills /solution /tests \
    && apt-get update \
    && apt-get install -y --no-install-recommends nodejs npm \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir \
        pytest==8.3.4 \
        pytest-json-ctrf==0.3.6 \
    && npm install -g typescript@5.6.3

COPY inputs/ /root/inputs/
