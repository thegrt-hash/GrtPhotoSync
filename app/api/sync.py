"""Sync control and history API."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.router import require_auth
from app.database.database import get_db
from app.database.models import MediaItem, SyncSession
from app.sync import manager

router = APIRouter(prefix="/api/sync", tags=["sync"])


@router.get("/status")
async def sync_status(_: str = Depends(require_auth)):
    return manager.progress.to_dict()


@router.post("/start")
async def sync_start(_: str = Depends(require_auth)):
    ok = await manager.start_sync()
    if not ok:
        raise HTTPException(409, "Sync is already running")
    return {"message": "Sync started"}


@router.post("/pause")
async def sync_pause(_: str = Depends(require_auth)):
    ok = manager.pause_sync()
    if not ok:
        raise HTTPException(409, "Sync is not currently running")
    return {"message": "Sync paused"}


@router.post("/resume")
async def sync_resume(_: str = Depends(require_auth)):
    ok = manager.resume_sync()
    if not ok:
        raise HTTPException(409, "Sync is not paused")
    return {"message": "Sync resumed"}


@router.post("/cancel")
async def sync_cancel(_: str = Depends(require_auth)):
    ok = manager.cancel_sync()
    if not ok:
        raise HTTPException(409, "No active sync to cancel")
    return {"message": "Sync cancelled"}


@router.get("/history")
async def sync_history(
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth),
):
    result = await db.execute(
        select(SyncSession).order_by(desc(SyncSession.started_at)).limit(limit)
    )
    rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "ended_at": r.ended_at.isoformat() if r.ended_at else None,
            "status": r.status,
            "items_discovered": r.items_discovered,
            "items_downloaded": r.items_downloaded,
            "items_skipped": r.items_skipped,
            "items_failed": r.items_failed,
            "bytes_transferred": r.bytes_transferred,
            "error_message": r.error_message,
        }
        for r in rows
    ]


@router.get("/errors")
async def sync_errors(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth),
):
    result = await db.execute(
        select(MediaItem)
        .where(MediaItem.status == "failed")
        .order_by(desc(MediaItem.updated_at))
        .limit(limit)
    )
    rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "google_id": r.google_id,
            "filename": r.filename,
            "error_count": r.error_count,
            "error_message": r.error_message,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }
        for r in rows
    ]


@router.post("/retry-failed")
async def retry_failed(
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth),
):
    """Reset failed items back to 'pending' so the next sync picks them up."""
    from sqlalchemy import update
    result = await db.execute(
        update(MediaItem)
        .where(MediaItem.status == "failed")
        .values(status="pending", error_count=0, error_message=None)
    )
    await db.commit()
    return {"reset": result.rowcount}
