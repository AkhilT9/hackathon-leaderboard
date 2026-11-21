FROM python:3.12-slim

# The hub uses only the Python standard library: nothing to pip install.
RUN useradd --system --uid 10001 --no-create-home hub && mkdir /data && chown hub /data
WORKDIR /app
COPY server_7400.py ./
COPY hub ./hub
COPY static ./static

ENV HUB_DATA_DIR=/data PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
USER hub
EXPOSE 7400
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7400/healthz', timeout=3)"
CMD ["python", "server_7400.py", "--host", "0.0.0.0", "--port", "7400"]
