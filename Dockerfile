# syntax=docker/dockerfile:1
FROM node:22-bookworm-slim AS frontend
WORKDIR /build/frontend
COPY frontend/package*.json ./
# Optional build secret supports verified downloads behind a managed proxy.
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/proxy_ca; fi; \
    npm ci --strict-ssl=true
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm AS dependencies
WORKDIR /build
COPY backend/requirements.txt ./
RUN python -m venv /opt/venv
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi; \
    /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

FROM python:3.12-slim-bookworm AS application
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    CULTIVATINATOR_DATA_DIR=/data \
    CULTIVATINATOR_FRONTEND_DIR=/app/frontend \
    CULTIVATINATOR_ENVIRONMENT=production
RUN groupadd --gid 10001 cultivatinator \
    && useradd --uid 10001 --gid 10001 --no-create-home cultivatinator \
    && mkdir /data && chown 10001:10001 /data
WORKDIR /app/backend
COPY --from=dependencies /opt/venv /opt/venv
COPY --chown=10001:10001 backend/ ./
COPY --from=frontend --chown=10001:10001 /build/frontend/dist /app/frontend
COPY --chown=10001:10001 LICENSE /app/LICENSE
USER 10001:10001
EXPOSE 8085
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8085/api/health', timeout=4)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8085", "--workers", "1"]
