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
    """Create tables. M1 ships without Alembic; add migrations before v1.0."""
    from . import models  # noqa: F401  (register models on Base)

    Base.metadata.create_all(engine)
