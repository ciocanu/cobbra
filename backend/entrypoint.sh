#!/bin/sh
set -e

echo "Running database migrations…"
alembic upgrade head

echo "Starting uvicorn (workers=${WORKERS:-2})…"
exec uvicorn main:app --host 0.0.0.0 --port 8000 --workers "${WORKERS:-2}"
