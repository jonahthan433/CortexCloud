# CortexCloud API — production image (FastAPI + local classical/hybrid solvers)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /opt/cortexcloud

# curl for the HEALTHCHECK; apt lists removed to keep the image slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY site ./site
COPY openapi.json .

# Non-root runtime user (uid 10001; unprivileged in the container)
RUN useradd -r -u 10001 cortex && chown -R cortex:cortex /opt/cortexcloud
USER cortex

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health >/dev/null || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]
