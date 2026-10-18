import os
import tempfile

# Point every test at a throwaway SQLite file before any module creates the engine,
# so tests that touch the database never reach a real one from the environment.
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(prefix="cobbra-tests-"), "test.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ.pop("PAYMENTS_ENABLED", None)
os.environ.pop("ANTHROPIC_API_KEY", None)
