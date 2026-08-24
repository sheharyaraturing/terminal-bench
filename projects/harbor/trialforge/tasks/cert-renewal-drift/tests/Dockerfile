# Verifier image for environment_mode = "separate". Harbor skips the tests/
# upload then, so this COPY is the only reason /tests/test.sh exists.
FROM python:3.12-slim
RUN pip install --no-cache-dir uv
COPY . /tests/
