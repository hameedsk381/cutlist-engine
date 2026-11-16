"""Database engine, session factory and schema init.

DATABASE_URL selects the backend:
  - sqlite:///./data/cutlist.db       (default, dev / tiny deployments)
  - postgresql+psycopg://user:pw@host/db  (production)
"""
from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.environ.get(
    "CUTLIST_DATABASE_URL", "sqlite:///./data/cutlist.db"
).strip()

_connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    # allow the worker process and the API process to share the file
    _connect_args = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, connect_args=_connect_args, pool_pre_ping=True)

if DATABASE_URL.startswith("sqlite"):
    db_file = DATABASE_URL.split("sqlite:///", 1)[1].split("?", 1)[0]
    Path(db_file).parent.mkdir(parents=True, exist_ok=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    """Create tables and add columns added after M1 (no Alembic yet)."""
    from . import models  # noqa: F401  (register models on Base)

    Base.metadata.create_all(engine)
    _ensure_columns()


def _ensure_columns() -> None:
    """Lightweight ALTERs for databases created by earlier versions.

    create_all() never alters existing tables, so M3 columns must be added
    explicitly. Works on SQLite and Postgres alike.
    """
    wanted: dict[str, list[str]] = {
        "users": [
            "email_verified BOOLEAN NOT NULL DEFAULT 0",
            "verification_token VARCHAR(128)",
        ],
        "projects": [
            "share_token VARCHAR(64)",
        ],
    }
    with engine.connect() as conn:
        from sqlalchemy import inspect

        existing_by_table = inspect(conn).get_table_names()
        for table, columns in wanted.items():
            if table not in existing_by_table:
                continue  # fresh DB — create_all already made everything
            existing = {c["name"] for c in inspect(conn).get_columns(table)}
            for col in columns:
                name = col.split()[0]
                if name not in existing:
                    conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {col}")
        conn.commit()
