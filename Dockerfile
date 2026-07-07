# P1.13 — Multi-stage production Dockerfile
# Target: Python 3.12 on Debian slim (stable, well-tested)

# ─── Build stage ─────────────────────────────────────────────
FROM python:3.12-slim-bookworm AS builder

WORKDIR /build
COPY backend/requirements.txt .

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir --target /deps -r requirements.txt \
    && rm -rf /root/.cache

# ─── Runtime stage ───────────────────────────────────────────
FROM python:3.12-slim-bookworm AS runtime

ARG UID=1001
ARG GID=1001
ARG BUILD_COMMIT=unknown
ARG BUILD_TIMESTAMP=unknown

LABEL org.opencontainers.image.title="Emsalist API"
LABEL org.opencontainers.image.version="${BUILD_COMMIT}"
LABEL org.opencontainers.image.revision="${BUILD_COMMIT}"
LABEL org.opencontainers.image.created="${BUILD_TIMESTAMP}"
LABEL org.opencontainers.image.description="Emsalist legal case analysis API — Phase 1"

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV EMSALIST_ENVIRONMENT=production
ENV EMSALIST_LOG_FORMAT=json
ENV EMSALIST_LOG_LEVEL=INFO
ENV EMSALIST_COMMIT="${BUILD_COMMIT}"
ENV EMSALIST_BUILD_TIMESTAMP="${BUILD_TIMESTAMP}"

RUN groupadd --gid "${GID}" emsalist \
    && useradd --uid "${UID}" --gid "${GID}" --no-create-home --shell /bin/false emsalist

COPY --from=builder /deps /usr/local/lib/python3.12/site-packages/

WORKDIR /app
COPY backend/ .

RUN mkdir -p /data/uploads /data/exports /data/backups /data/logs /app/case_store \
    && chown -R emsalist:emsalist /app /data

USER emsalist

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/live')" || exit 1

VOLUME ["/data/uploads", "/data/exports", "/data/backups"]

CMD ["python", "-m", "uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--proxy-headers", \
     "--forwarded-allow-ips", "*" ]
