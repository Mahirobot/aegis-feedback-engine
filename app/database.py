import threading
from typing import Generator

from sqlalchemy.pool import NullPool
from sqlmodel import Session, create_engine

from app.config import settings
from app.logging import setup_logging

logger = setup_logging()

# GLOBAL LOCK: Required for SQLite concurrency in async context
db_write_lock = threading.Lock()

# DB ENGINE
engine = create_engine(
    settings.DATABASE_URL, connect_args={"check_same_thread": False}, poolclass=NullPool
)


def get_session() -> Generator[Session, None, None]:
    """Dependency to provide a DB session."""
    with Session(engine) as session:
        yield session


def enable_wal_mode():
    """Enable Write-Ahead Logging for better SQLite concurrency."""
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("PRAGMA journal_mode=WAL;")
    except Exception as e:
        logger.warning(f"WAL mode config failed: {e}")
