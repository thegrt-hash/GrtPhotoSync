"""Browser API – browse source (Google Photos) and destination (local) files,
serve local thumbnails, and compare both sides."""

import mimetypes
import os
from typing import Optional

import aiofiles
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.router import require_auth
from app.config import settings
from app.database.database import get_db
from app.database.models import Album, AlbumMembership, MediaItem
from app.google import photos_api
from app.storage.metadata import get_cached_thumbnail
from app.storage.organizer import list_local_files, year_month_dir

router = APIRouter(prefix="/api/browse", tags=["browse"])

IMAGE_MIMES = {"image/jpeg", "image/png", "image/gif", "image/webp", "image/heic"}


# ── Albums ─────────────────────────────────────────────────────────────────────

@router.get("/albums")
async def list_albums(
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth),
):
    result = await db.execute(select(Album).order_by(Album.title))
    return [
        {"id": a.id, "google_id": a.google_id, "title": a.title, "item_count": a.item_count}
        for a in result.scalars().all()
    ]


# ── Source (Google Photos) ─────────────────────────────────────────────────────

@router.get("/source")
async def browse_source(
    page_token: Optional[str] = None,
    page_size: int = Query(default=50, le=100),
    _: str = Depends(require_auth),
):
    """Return a page of media items from Google Photos (with thumbnail URLs)."""
    try:
        data = await photos_api.list_media_items_page(page_token=page_token, page_size=page_size)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))

    items = []
    for item in data.get("mediaItems", []):
        base_url = item.get("baseUrl", "")
        creation_time = photos_api.parse_creation_time(item)
        items.append({
            "google_id": item["id"],
            "filename": item.get("filename"),
            "mime_type": item.get("mimeType"),
            "thumbnail_url": photos_api.thumbnail_url(base_url, 256, 256) if base_url else None,
            "creation_time": creation_time.isoformat() if creation_time else None,
            "is_video": photos_api.is_video(item),
        })

    return {
        "items": items,
        "next_page_token": data.get("nextPageToken"),
    }


# ── Destination (local) ────────────────────────────────────────────────────────

@router.get("/local")
async def browse_local(
    year: Optional[int] = None,
    month: Optional[int] = None,
    album_id: Optional[int] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth),
):
    """Browse locally downloaded photos by year/month or album."""
    query = select(MediaItem).where(MediaItem.status == "completed")

    if year:
        query = query.where(MediaItem.year == year)
    if month:
        query = query.where(MediaItem.month == month)
    if album_id:
        query = query.join(
            AlbumMembership, AlbumMembership.media_item_id == MediaItem.id
        ).where(AlbumMembership.album_id == album_id)

    # Pagination
    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar_one()

    query = query.order_by(MediaItem.creation_time.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    items = result.scalars().all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "id": m.id,
                "google_id": m.google_id,
                "filename": m.filename,
                "mime_type": m.mime_type,
                "local_path": m.local_path,
                "creation_time": m.creation_time.isoformat() if m.creation_time else None,
                "year": m.year,
                "month": m.month,
                "file_size": m.file_size_local,
                "latitude": m.latitude,
                "longitude": m.longitude,
                "camera_make": m.camera_make,
                "camera_model": m.camera_model,
                "thumbnail_url": f"/api/browse/thumbnail/{m.id}",
            }
            for m in items
        ],
    }


@router.get("/years")
async def list_years(
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth),
):
    result = await db.execute(
        select(distinct(MediaItem.year), MediaItem.month)
        .where(MediaItem.status == "completed", MediaItem.year.isnot(None))
        .order_by(MediaItem.year.desc(), MediaItem.month.asc())
    )
    rows = result.all()
    years: dict = {}
    for year, month in rows:
        years.setdefault(year, []).append(month)
    return [{"year": y, "months": m} for y, m in sorted(years.items(), reverse=True)]


@router.get("/thumbnail/{media_id}")
async def local_thumbnail(
    media_id: int,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth),
):
    """Serve (or generate) a thumbnail for a locally stored media item."""
    result = await db.execute(select(MediaItem).where(MediaItem.id == media_id))
    media = result.scalar_one_or_none()
    if not media or not media.local_path or not os.path.exists(media.local_path):
        raise HTTPException(404, "File not found")

    thumb_path = get_cached_thumbnail(media.local_path, settings.THUMBNAIL_CACHE_PATH)
    if thumb_path:
        return FileResponse(thumb_path, media_type="image/jpeg")

    # Fallback: stream the original (e.g., for video files where thumb failed)
    mime = media.mime_type or "application/octet-stream"
    return FileResponse(media.local_path, media_type=mime)


@router.get("/file/{media_id}")
async def stream_local_file(
    media_id: int,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth),
):
    """Stream the full local file for in-browser preview."""
    result = await db.execute(select(MediaItem).where(MediaItem.id == media_id))
    media = result.scalar_one_or_none()
    if not media or not media.local_path or not os.path.exists(media.local_path):
        raise HTTPException(404, "File not found")

    # Security: ensure path is within destination
    real = os.path.realpath(media.local_path)
    dest_real = os.path.realpath(settings.DESTINATION_PATH)
    if not real.startswith(dest_real + os.sep):
        raise HTTPException(403, "Access denied")

    mime = media.mime_type or mimetypes.guess_type(media.local_path)[0] or "application/octet-stream"
    return FileResponse(media.local_path, media_type=mime)


# ── Comparison helper ─────────────────────────────────────────────────────────

@router.get("/compare/{google_id}")
async def compare_item(
    google_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth),
):
    """Compare the Google Photos source item with the local copy."""
    result = await db.execute(select(MediaItem).where(MediaItem.google_id == google_id))
    media = result.scalar_one_or_none()

    local_info = None
    if media and media.local_path and os.path.exists(media.local_path):
        local_info = {
            "exists": True,
            "path": media.local_path,
            "size": os.path.getsize(media.local_path),
            "thumbnail_url": f"/api/browse/thumbnail/{media.id}",
            "stream_url": f"/api/browse/file/{media.id}",
        }
    else:
        local_info = {"exists": False}

    try:
        source = await photos_api.get_media_item(google_id)
        base_url = source.get("baseUrl", "")
        source_info = {
            "google_id": google_id,
            "filename": source.get("filename"),
            "mime_type": source.get("mimeType"),
            "thumbnail_url": photos_api.thumbnail_url(base_url, 512, 512),
            "creation_time": source.get("mediaMetadata", {}).get("creationTime"),
        }
    except Exception:
        source_info = {"error": "Could not fetch from Google Photos"}

    return {"source": source_info, "local": local_info}
