#!/bin/sh
set -e

echo "Checking database state…"
python - <<'EOF'
from sqlalchemy import inspect, text
from database import engine, Base
import models  # noqa: F401

inspector = inspect(engine)
tables = inspector.get_table_names()

if 'alembic_version' not in tables:
    print("Fresh database — creating all tables and stamping Alembic head…")
    Base.metadata.create_all(bind=engine)
    # Mark the DB as already at the latest Alembic revision so upgrade head is a no-op
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL, CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"))
        conn.execute(text("DELETE FROM alembic_version"))
        conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('edcd22bd7c32')"))
    print("Done.")
else:
    print("Existing database — running incremental Alembic migrations…")
EOF

alembic upgrade head

echo "Starting uvicorn (workers=${WORKERS:-2})…"
exec uvicorn main:app --host 0.0.0.0 --port 8000 --workers "${WORKERS:-2}"
