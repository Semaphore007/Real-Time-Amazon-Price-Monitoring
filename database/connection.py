"""
Database connection bootstrapping.

Supports both:
  - PostgreSQL (production)  — full schema from schema.sql
  - SQLite     (dev/testing) — in-memory or file-based, ORM-only (no PG views)
"""
from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from database.models import Base

logger = logging.getLogger(__name__)

_SESSION_FACTORY: sessionmaker | None = None

# Path to the hand-crafted SQL schema (indexes, views, functions)
_SCHEMA_SQL = Path(__file__).with_name("schema.sql")


def init_database(database_url: str) -> sessionmaker:
    """
    Initialize the engine + session factory (idempotent).

    For PostgreSQL:  runs schema.sql on first boot to create views & indexes.
    For SQLite:      uses SQLAlchemy's metadata.create_all (no views).
    """
    global _SESSION_FACTORY

    if _SESSION_FACTORY is not None:
        return _SESSION_FACTORY

    is_postgres = database_url.startswith("postgresql")
    connect_args: dict = {}

    if not is_postgres:
        # SQLite: allow same-thread access for dev servers
        connect_args["check_same_thread"] = False

    engine = create_engine(
        database_url,
        pool_pre_ping=True,
        future=True,
        connect_args=connect_args,
        # Postgres connection pool tuning
        **({"pool_size": 5, "max_overflow": 10} if is_postgres else {}),
    )

    if is_postgres:
        _apply_postgres_schema(engine)
    else:
        # For SQLite / testing: ORM-managed tables only (no views/functions)
        Base.metadata.create_all(engine)

    _SESSION_FACTORY = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        future=True,
        expire_on_commit=False,
    )
    logger.info("Database initialized: %s", _redact(database_url))
    return _SESSION_FACTORY


def get_session_factory(database_url: str) -> sessionmaker:
    return init_database(database_url)


def refresh_materialized_views(session_factory: sessionmaker) -> None:
    """
    Refresh materialized views that power dashboard aggregations.
    Call from a scheduler (e.g. every hour).
    """
    with session_factory() as session:
        try:
            session.execute(
                text("REFRESH MATERIALIZED VIEW CONCURRENTLY mvw_category_price_summary")
            )
            session.commit()
            logger.info("Materialized views refreshed.")
        except Exception as exc:
            logger.warning("Could not refresh materialized views: %s", exc)
            session.rollback()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _apply_postgres_schema(engine: Engine) -> None:
    """
    Run schema.sql idempotently (all statements use IF NOT EXISTS / OR REPLACE).
    """
    if not _SCHEMA_SQL.exists():
        logger.warning("schema.sql not found — falling back to ORM create_all")
        Base.metadata.create_all(engine)
        return

    sql = _SCHEMA_SQL.read_text(encoding="utf-8")
    with engine.begin() as conn:
        conn.execute(text(sql))
    logger.info("PostgreSQL schema applied from %s", _SCHEMA_SQL)


def _redact(url: str) -> str:
    """Hide password in connection string for safe logging."""
    try:
        from urllib.parse import urlparse, urlunparse
        parsed = urlparse(url)
        if parsed.password:
            netloc = parsed.netloc.replace(parsed.password, "***")
            return urlunparse(parsed._replace(netloc=netloc))
    except Exception:
        pass
    return url
