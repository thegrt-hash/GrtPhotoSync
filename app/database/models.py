"""ORM models for the application database."""

from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Boolean, DateTime, Float, Integer, String, Text,
    ForeignKey, Index, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.database import Base


class MediaItem(Base):
    """Tracks every Google Photos media item."""
    __tablename__ = "media_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    google_id: Mapped[str] = mapped_column(String(256), unique=True, nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)

    # Date from Google Photos metadata
    creation_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    month: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)

    # Location metadata (from Google API response)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Camera info
    camera_make: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    camera_model: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    # Local file info
    local_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    file_size_remote: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    file_size_local: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Download state: pending | downloading | completed | failed | skipped
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Sync metadata
    last_checked: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    downloaded_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    # Google album memberships (junction)
    album_memberships: Mapped[list["AlbumMembership"]] = relationship(
        back_populates="media_item", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_media_year_month", "year", "month"),
        Index("ix_media_status_creation", "status", "creation_time"),
    )


class Album(Base):
    """Tracks Google Photos albums."""
    __tablename__ = "albums"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    google_id: Mapped[str] = mapped_column(String(256), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    local_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    item_count: Mapped[int] = mapped_column(Integer, default=0)
    last_synced: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    memberships: Mapped[list["AlbumMembership"]] = relationship(
        back_populates="album", cascade="all, delete-orphan"
    )


class AlbumMembership(Base):
    """Junction table: which media items belong to which albums."""
    __tablename__ = "album_memberships"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    album_id: Mapped[int] = mapped_column(Integer, ForeignKey("albums.id"), nullable=False)
    media_item_id: Mapped[int] = mapped_column(Integer, ForeignKey("media_items.id"), nullable=False)

    album: Mapped["Album"] = relationship(back_populates="memberships")
    media_item: Mapped["MediaItem"] = relationship(back_populates="album_memberships")

    __table_args__ = (
        Index("ix_album_media", "album_id", "media_item_id", unique=True),
    )


class SyncSession(Base):
    """Records each sync run for history and auditing."""
    __tablename__ = "sync_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Status: running | completed | failed | cancelled
    status: Mapped[str] = mapped_column(String(32), default="running")

    items_discovered: Mapped[int] = mapped_column(Integer, default=0)
    items_downloaded: Mapped[int] = mapped_column(Integer, default=0)
    items_skipped: Mapped[int] = mapped_column(Integer, default=0)
    items_failed: Mapped[int] = mapped_column(Integer, default=0)
    bytes_transferred: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class AppSetting(Base):
    """Persistent key-value settings (changeable at runtime via the web UI)."""
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
