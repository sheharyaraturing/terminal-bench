FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /root

RUN mkdir -p /logs/agent /logs/verifier /logs/artifacts /root /skills \
    && pip install --no-cache-dir \
        pytest==8.3.4 \
        pytest-json-ctrf==0.3.6

COPY inputs/palette.json /root/palette.json
