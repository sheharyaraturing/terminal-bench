# Verifier image for [verifier].environment_mode = "separate", where harbor sets skip_tests_upload=True (harbor/trial/trial.py:618) and the COPY below is the only reason /tests/test.sh exists inside the container; deliberately not the mcp-atlas image, since the judge reads the recorded answer from /logs/artifacts and needs only python and outbound network to OpenRouter.
FROM python:3.12-slim
RUN pip install --no-cache-dir uv
COPY . /tests/
