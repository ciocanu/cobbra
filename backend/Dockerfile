# ── Stage 1: install dependencies into an isolated virtual env ────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# ── Stage 2: minimal production runtime ───────────────────────────────────────
FROM python:3.12-slim AS final

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Non-root user — created before COPY --chown so the names resolve
RUN groupadd -r appgroup \
 && useradd -r -g appgroup -s /sbin/nologin -d /app --no-create-home appuser

WORKDIR /app

# Virtual env from builder (root-owned; read-only access is enough)
COPY --from=builder /opt/venv /opt/venv

# Application source — only what the server needs at runtime
COPY --chown=appuser:appgroup alembic/         ./alembic/
COPY --chown=appuser:appgroup alembic.ini      .
COPY --chown=appuser:appgroup parsers/         ./parsers/
COPY --chown=appuser:appgroup routes/          ./routes/
COPY --chown=appuser:appgroup utils/           ./utils/
COPY --chown=appuser:appgroup auth.py          .
COPY --chown=appuser:appgroup database.py      .
COPY --chown=appuser:appgroup email_service.py .
COPY --chown=appuser:appgroup main.py          .
COPY --chown=appuser:appgroup models.py        .
COPY --chown=appuser:appgroup schemas.py       .
COPY --chown=appuser:appgroup utils.py         .
COPY --chown=appuser:appgroup entrypoint.sh    .

RUN chmod +x /app/entrypoint.sh

USER appuser

EXPOSE 8000

# exec in entrypoint.sh replaces the shell with uvicorn (PID 1 → clean signals)
ENTRYPOINT ["/app/entrypoint.sh"]
