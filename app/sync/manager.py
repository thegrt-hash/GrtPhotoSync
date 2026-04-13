"""Core sync manager – orchestrates discovery, download, validation, and DB updates.

State machine
─────────────
  idle  →  running  →  idle
           ↓
        paused  →  running
           ↓
        cancelled  →  idle
"""

import asyncio
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.database import get_session_factory
from app.database.models import Album, AlbumMembership, MediaItem, SyncSession
from app.google import photos_api
from app.google.auth import is_connected
from app.storage.organizer import resolve_local_path, ensure_album_link
from app.sync.transfer import download_file
from app.sync.validator import validate_file

logger = logging.getLogger(__name__)


class SyncState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    CANCELLED = "cancelled"


class SyncProgress:
    def __init__(self):
        self.state: SyncState = SyncState.IDLE
        self.session_id: Optional[int] = None
        self.discovered: int = 0
        self.downloaded: int = 0
        self.skipped: int = 0
        self.failed: int = 0
        self.bytes_transferred: int = 0
        self.current_file: Optional[str] = None
        self.error: Optional[str] = None
        self.started_at: Optional[datetime] = None
        self.ended_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "state": self.state,
            "session_id": self.session_id,
            "discovered": self.discovered,
            "downloaded": self.downloaded,
            "skipped": self.skipped,
            "failed": self.failed,
            "bytes_transferred": self.bytes_transferred,
            "current_file": self.current_file,
            "error": self.error,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
        }


# Global progress object – read by the status API
progress = SyncProgress()

# Event to pause/resume
_pause_event = asyncio.Event()
_pause_event.set()   # Initially not paused

# Cancellation flag
_cancel_flag = False


async def start_sync() -> bool:
    """Start a new sync run. Returns False if already running."""
    global _cancel_flag
    if progress.state == SyncState.RUNNING:
        return False
    _cancel_flag = False
    _pause_event.set()
    asyncio.create_task(_run_sync())
    return True


def pause_sync() -> bool:
    if progress.state != SyncState.RUNNING:
        return False
    _pause_event.clear()
    progress.state = SyncState.PAUSED
    return True


def resume_sync() -> bool:
    if progress.state != SyncState.PAUSED:
        return False
    _pause_event.set()
    progress.state = SyncState.RUNNING
    return True


def cancel_sync() -> bool:
    global _cancel_flag
    if progress.state not in (SyncState.RUNNING, SyncState.PAUSED):
        return False
    _cancel_flag = True
    _pause_event.set()   # Unblock if paused so the loop can exit
    progress.state = SyncState.CANCELLED
    return True


# ── Main sync task ────────────────────────────────────────────────────────────

async def _run_sync():
    global _cancel_flag
    if not is_connected():
        progress.error = "Google account not connected"
        return

    progress.state = SyncState.RUNNING
    progress.started_at = datetime.now(timezone.utc)
    progress.ended_at = None
    progress.discovered = progress.downloaded = progress.skipped = progress.failed = 0
    progress.bytes_transferred = 0
    progress.error = None

    factory = get_session_factory()
    async with factory() as db:
        sync_row = SyncSession()
        db.add(sync_row)
        await db.commit()
        await db.refresh(sync_row)
        progress.session_id = sync_row.id

        try:
            await _sync_albums(db)
            await _sync_media_items(db, sync_row)
            sync_row.status = "completed"
        except asyncio.CancelledError:
            sync_row.status = "cancelled"
        except Exception as exc:
            logger.exception("Sync failed: %s", exc)
            sync_row.status = "failed"
            sync_row.error_message = str(exc)
            progress.error = str(exc)
        finally:
            sync_row.ended_at = datetime.now(timezone.utc)
            sync_row.items_discovered = progress.discovered
            sync_row.items_downloaded = progress.downloaded
            sync_row.items_skipped = progress.skipped
            sync_row.items_failed = progress.failed
            sync_row.bytes_transferred = progress.bytes_transferred
            await db.commit()

    progress.state = SyncState.IDLE
    progress.ended_at = datetime.now(timezone.utc)
    progress.current_file = None
    logger.info(
        "Sync complete – discovered=%d downloaded=%d skipped=%d failed=%d",
        progress.discovered, progress.downloaded, progress.skipped, progress.failed,
    )


async def _check_pause_cancel():
    """Wait if paused; raise if cancelled."""
    await _pause_event.wait()
    if _cancel_flag:
        raise asyncio.CancelledError("Sync cancelled by user")


async def _sync_albums(db: AsyncSession):
    """Discover albums and ensure they're in the DB."""
    async for album_data in photos_api.iter_all_albums():
        await _check_pause_cancel()
        google_id = album_data["id"]
        title = album_data.get("title", "Untitled")

        result = await db.execute(select(Album).where(Album.google_id == google_id))
        album = result.scalar_one_or_none()
        if album is None:
            album = Album(google_id=google_id, title=title)
            db.add(album)
        else:
            album.title = title
        await db.flush()

        # Persist album items into the junction table
        async for item in photos_api.iter_album_items(google_id):
            await _check_pause_cancel()
            await _upsert_media_item(db, item, album=album)

    await db.commit()


async def _sync_media_items(db: AsyncSession, sync_row: SyncSession):
    """Walk the entire library and download anything not yet saved."""
    # Determine last sync time for incremental updates
    last_sync = None
    prev = await db.execute(
        select(SyncSession)
        .where(SyncSession.status == "completed")
        .order_by(SyncSession.ended_at.desc())
        .limit(1)
    )
    prev_row = prev.scalar_one_or_none()
    if prev_row and prev_row.ended_at:
        last_sync = prev_row.ended_at

    async for item in photos_api.iter_all_media_items(after=last_sync):
        await _check_pause_cancel()
        media = await _upsert_media_item(db, item)
        progress.discovered += 1

        if media.status == "completed":
            progress.skipped += 1
            continue

        await _download_item(db, media, item)

    await db.commit()


async def _upsert_media_item(
    db: AsyncSession, item: dict, album: Optional[Album] = None
) -> MediaItem:
    """Insert or update a MediaItem row from a Google Photos API response dict."""
    google_id = item["id"]
    result = await db.execute(select(MediaItem).where(MediaItem.google_id == google_id))
    media = result.scalar_one_or_none()

    creation_time = photos_api.parse_creation_time(item)
    lat, lon = photos_api.extract_location(item)
    photo_meta = item.get("mediaMetadata", {}).get("photo", {})

    if media is None:
        media = MediaItem(
            google_id=google_id,
            filename=item.get("filename", "unknown"),
            mime_type=item.get("mimeType", "application/octet-stream"),
            creation_time=creation_time,
            year=creation_time.year if creation_time else None,
            month=creation_time.month if creation_time else None,
            latitude=lat,
            longitude=lon,
            camera_make=photo_meta.get("cameraMake"),
            camera_model=photo_meta.get("cameraModel"),
            status="pending",
        )
        db.add(media)
    else:
        # Refresh mutable fields
        media.filename = item.get("filename", media.filename)
        media.last_checked = datetime.now(timezone.utc)

    await db.flush()

    # Link to album if provided
    if album is not None:
        exists = await db.execute(
            select(AlbumMembership).where(
                AlbumMembership.album_id == album.id,
                AlbumMembership.media_item_id == media.id,
            )
        )
        if exists.scalar_one_or_none() is None:
            db.add(AlbumMembership(album_id=album.id, media_item_id=media.id))
            await db.flush()

    return media


async def _download_item(db: AsyncSession, media: MediaItem, item: dict):
    """Download a single media item, validate, and update DB."""
    is_video = photos_api.is_video(item)
    base_url = item.get("baseUrl", "")
    if not base_url:
        # Refresh the item to get a fresh baseUrl
        fresh = await photos_api.get_media_item(media.google_id)
        base_url = fresh.get("baseUrl", "")

    download_url = photos_api.video_download_url(base_url) if is_video else photos_api.photo_download_url(base_url)
    local_path = resolve_local_path(media, settings.DESTINATION_PATH)

    # Already on disk?
    import os
    if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
        media.status = "completed"
        media.local_path = local_path
        media.downloaded_at = datetime.now(timezone.utc)
        progress.skipped += 1
        await db.flush()
        return

    media.status = "downloading"
    progress.current_file = media.filename
    await db.flush()

    try:
        def _on_progress(n: int):
            progress.bytes_transferred += n

        bytes_written = await download_file(download_url, local_path, on_progress=_on_progress)

        if validate_file(local_path):
            media.status = "completed"
            media.local_path = local_path
            media.file_size_local = os.path.getsize(local_path)
            media.downloaded_at = datetime.now(timezone.utc)
            media.error_count = 0
            media.error_message = None
            progress.downloaded += 1

            # Create album symlinks
            result = await db.execute(
                select(AlbumMembership).where(AlbumMembership.media_item_id == media.id)
            )
            for membership in result.scalars().all():
                album_result = await db.execute(
                    select(Album).where(Album.id == membership.album_id)
                )
                album = album_result.scalar_one_or_none()
                if album:
                    ensure_album_link(local_path, album.title, settings.DESTINATION_PATH, media.filename)
        else:
            media.status = "failed"
            media.error_count += 1
            media.error_message = "Validation failed after download"
            progress.failed += 1

    except Exception as exc:
        logger.error("Failed to download %s: %s", media.filename, exc)
        media.status = "failed" if media.error_count >= settings.MAX_RETRIES else "pending"
        media.error_count += 1
        media.error_message = str(exc)
        progress.failed += 1

    await db.flush()
