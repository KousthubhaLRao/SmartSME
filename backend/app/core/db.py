"""Engine and session factory.

The declarative `Base` lives in `app.models.base`, not here, so that importing
the database layer never drags in the ORM models.
"""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .config import settings

# pool_pre_ping keeps long-lived dev sessions alive across database restarts.
#
# The pool size is the real concurrency limit of the API: a request holds its
# connection from the first query to the response, so `pool_size + max_overflow`
# is how many requests can be in flight at once. Left at SQLAlchemy's default of
# 5 + 10, a couple of hundred users queue behind fifteen connections and wait
# out the 30-second timeout.
#
# Sizing: keep (pool_size + max_overflow) x uvicorn workers below Postgres's
# `max_connections`, which defaults to 100.
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_timeout=settings.db_pool_timeout,
    pool_recycle=settings.db_pool_recycle,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request, always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
