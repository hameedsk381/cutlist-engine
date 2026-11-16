"""SQLAlchemy models: User, Project, Job."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    plan: Mapped[str] = mapped_column(String(32), default="free")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verification_token: Mapped[str | None] = mapped_column(String(128), nullable=True)
    brand_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Studio details printed on client quotes (see brand.py)."""

    projects: Mapped[list["Project"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    api_keys: Mapped[list["ApiKey"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    original_filename: Mapped[str] = mapped_column(String(255), default="model")
    model_path: Mapped[str] = mapped_column(String(1024), default="")
    """Absolute path of the uploaded model file. Set after the row is flushed
    (the storage path needs the row id); committed together with the row."""
    config_json: Mapped[str] = mapped_column(Text, default="{}")
    """ProcessConfig kwargs as JSON (sheet size, kerf, confidence...)."""
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    share_token: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True, index=True)
    """Public token for the shareable quote page (read-only)."""

    user: Mapped[User] = relationship(back_populates="projects")
    jobs: Mapped[list["Job"]] = relationship(
        back_populates="project", cascade="all, delete-orphan",
        order_by="Job.created_at.desc()",
    )


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    """queued | processing | done | failed"""
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    artifacts_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    """[{"name": ..., "path": ...}] relative to the project dir."""
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Serialized ProcessResult summary (same shape as /api/process summary)."""
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped[Project] = relationship(back_populates="jobs")


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120), default="API key")
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    """sha256 hex of the full key — the raw key is never stored."""
    key_prefix: Mapped[str] = mapped_column(String(16))
    """First characters (e.g. 'ckl_a1b2') shown in the dashboard."""
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="api_keys")


class OffcutStock(Base):
    """A leftover piece saved from a finished project (the shop's offcut shelf).

    Lifecycle: 'available' → 'reserved' (attached to a new project, its dims
    injected into that job's config) → 'used' (job succeeded) — or back to
    'available' if the job failed.
    """
    __tablename__ = "offcut_stock"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    length: Mapped[float] = mapped_column(default=0.0)
    width: Mapped[float] = mapped_column(default=0.0)
    thickness: Mapped[float] = mapped_column(default=18.0)
    material: Mapped[str] = mapped_column(String(64), default="default")
    source_project_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    """Project whose leftovers produced this piece."""
    project_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    """Project currently reserving/using this piece (None when available)."""
    status: Mapped[str] = mapped_column(String(16), default="available")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    @property
    def area_m2(self) -> float:
        return round(self.length * self.width / 1_000_000.0, 4)
