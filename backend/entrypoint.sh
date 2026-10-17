#!/bin/sh
set -e

echo "Checking database state…"
python - <<'EOF'
from sqlalchemy import inspect
from database import engine, Base
import models  # noqa: F401

inspector = inspect(engine)
tables = inspector.get_table_names()

if 'alembic_version' not in tables:
    print("Fresh database — creating all tables and stamping Alembic head…")
    Base.metadata.create_all(bind=engine)
    # create_all() already built the latest schema, so mark the DB as being at the
    # newest migration and `upgrade head` below is a no-op. Stamp "head" rather than
    # a hard-coded revision: a stale one made upgrade re-apply migrations whose
    # columns create_all() had already created ("duplicate column"), crash-looping
    # the backend on any fresh install.
    from alembic import command
    from alembic.config import Config
    command.stamp(Config("alembic.ini"), "head")
    print("Done.")
else:
    print("Existing database — running incremental Alembic migrations…")
EOF

alembic upgrade head

echo "Starting uvicorn (workers=${WORKERS:-2})…"
exec uvicorn main:app --host 0.0.0.0 --port 8000 --workers "${WORKERS:-2}"
