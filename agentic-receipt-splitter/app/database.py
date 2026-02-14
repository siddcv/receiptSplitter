"""
Database and checkpointer initialization.

This module wires up the Postgres connection (via psycopg) and the LangGraph
PostgresSaver checkpointer, which persists graph state per thread_id.

Usage:
    from app.database import get_checkpointer, ensure_db_ready, get_connection
    ensure_db_ready()  # optional: verifies DB connectivity
    checkpointer = get_checkpointer()
"""

from __future__ import annotations

import os
from typing import Optional

from dotenv import load_dotenv
from psycopg import connect
from psycopg.errors import DuplicatePreparedStatement, OperationalError
# Import path for the Postgres checkpointer in LangGraph
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg_pool import ConnectionPool


_CHECKPOINTER: Optional[PostgresSaver] = None


def _load_env() -> None:
    """Load environment variables from .env if present."""
    # Safe to call multiple times; no-op if already loaded
    load_dotenv(override=False)


def get_database_url() -> str:
    _load_env()
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set in environment/.env")
    return url


def ensure_db_ready(timeout_seconds: int = 10) -> None:
    """Attempt a simple connection and ping to verify DB is reachable."""
    dsn = get_database_url()
    try:
        with connect(
            dsn,
            connect_timeout=timeout_seconds,
            prepare_threshold=None,
            autocommit=True,
        ) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
                cur.fetchone()
    except (OperationalError, DuplicatePreparedStatement) as e:
        raise RuntimeError(f"Unable to connect to Postgres: {e}")


def get_connection(**kwargs):
    """Return a psycopg connection with prepared statements disabled.

    Supabase's transaction pooler (Supavisor) multiplexes connections, so
    prepared statements created on one backend aren't visible to others.
    Setting prepare_threshold=None tells psycopg to completely disable
    server-side prepared statements (0 means "prepare on first use",
    which still triggers PREPARE and causes DuplicatePreparedStatement
    errors with transaction-mode poolers).

    All keyword arguments are forwarded to psycopg.connect().
    """
    dsn = get_database_url()
    return connect(dsn, prepare_threshold=None, **kwargs)


def get_checkpointer() -> PostgresSaver:
    """Return a singleton PostgresSaver bound to DATABASE_URL.

    If the saver provides a setup()/initialize() method, we invoke it to
    ensure the backing table(s) exist.
    """
    global _CHECKPOINTER
    if _CHECKPOINTER is None:
        dsn = get_database_url()
        # Initialize a psycopg connection pool with autocommit enabled.
        # Autocommit is required because the checkpointer migrations use
        # CREATE INDEX CONCURRENTLY, which cannot run inside a transaction.
        # It also ensures regular upserts are committed without explicit commits.
        # prepare_threshold=None fully disables prepared statements (required
        # for Supabase transaction pooler / Supavisor on port 6543).

        pool = ConnectionPool(
            dsn,
            kwargs={"autocommit": True, "prepare_threshold": None},
        )
        _CHECKPOINTER = PostgresSaver(pool)
        # Initialize schema if supported by the library version
        for method_name in ("setup", "initialize", "init", "create_tables"):
            setup_method = getattr(_CHECKPOINTER, method_name, None)
            if callable(setup_method):
                setup_method()
                break
    return _CHECKPOINTER