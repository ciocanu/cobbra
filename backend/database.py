from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./cycling.db")

_is_sqlite = DATABASE_URL.startswith("sqlite")

engine = create_engine(
    DATABASE_URL,
    # SQLite requires check_same_thread=False when shared across threads.
    # PostgreSQL uses connection pooling instead; pool_pre_ping validates
    # connections before use to handle idle-connection drops from the server.
    connect_args={"check_same_thread": False} if _is_sqlite else {},
    pool_pre_ping=not _is_sqlite,
)

if _is_sqlite:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        # WAL mode: allows concurrent reads while a write is in progress,
        # eliminating most "database is locked" errors from parallel requests.
        cur.execute("PRAGMA journal_mode=WAL")
        # Wait up to 10 s for a write lock instead of failing immediately.
        # Handles the race between the upload background task and page-load GETs.
        cur.execute("PRAGMA busy_timeout=10000")
        cur.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
