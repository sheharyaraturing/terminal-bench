# Verifier image, used only when [verifier].environment_mode = "separate".
#
# In separate mode Harbor sets skip_tests_upload=True (harbor/trial/trial.py:618) on the
# assumption that the verifier image ALREADY owns /tests/test.sh - it does not upload
# tests/ at run time. So this directory is the build context and the COPY below is the
# only reason /tests/test.sh exists inside the container.
#
# Deliberately NOT the mcp-atlas image: the judge needs python and outbound network to
# reach OpenRouter, and nothing else. It reads the recorded answer from /logs/artifacts
# and never touches the MCP sandbox.
FROM python:3.12-slim
RUN pip install --no-cache-dir uv
COPY . /tests/
