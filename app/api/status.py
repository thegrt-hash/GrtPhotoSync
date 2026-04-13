"""Overall app status and Google OAuth connection endpoints."""

import os
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.router import require_auth
from app.config import settings
from app.database.database import get_db
from app.database.models import MediaItem
from app.google.auth import exchange_code, get_auth_url, is_connected, revoke_credentials
from app.sync.manager import progress

router = APIRouter(tags=["status"])


@router.get("/api/status/health")
async def health():
    """Simple health-check endpoint (no auth required – used by Docker HEALTHCHECK)."""
    return {"status": "ok"}


@router.get("/api/status")
async def app_status(
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth),
):
    """Return high-level application status."""
    counts = await db.execute(
        select(MediaItem.status, func.count(MediaItem.id))
        .group_by(MediaItem.status)
    )
    status_map = dict(counts.all())

    dest = settings.DESTINATION_PATH
    disk_free = None
    disk_total = None
    try:
        stat = os.statvfs(dest)
        disk_free = stat.f_bavail * stat.f_frsize
        disk_total = stat.f_blocks * stat.f_frsize
    except Exception:
        pass

    return {
        "google_connected": is_connected(),
        "destination_path": dest,
        "disk_free_bytes": disk_free,
        "disk_total_bytes": disk_total,
        "media_counts": {
            "total": sum(status_map.values()),
            "completed": status_map.get("completed", 0),
            "pending": status_map.get("pending", 0),
            "failed": status_map.get("failed", 0),
            "downloading": status_map.get("downloading", 0),
        },
        "sync": progress.to_dict(),
        "settings": {
            "speed_limit_mbps": settings.SPEED_LIMIT_MBPS,
            "sync_interval_minutes": settings.SYNC_INTERVAL_MINUTES,
        },
    }


# ── Google OAuth flow ─────────────────────────────────────────────────────────

@router.get("/api/google/status")
async def google_status(_: str = Depends(require_auth)):
    return {"connected": is_connected()}


@router.get("/api/google/auth-url")
async def google_auth_url(_: str = Depends(require_auth)):
    url, state = get_auth_url()
    return {"auth_url": url, "state": state}


@router.get("/api/google/callback")
async def google_callback(request: Request):
    """Handle the OAuth2 redirect from Google.

    No authentication check here – the callback is initiated by Google.
    We redirect to the dashboard after saving the token.
    """
    code = request.query_params.get("code")
    if not code:
        return RedirectResponse("/?error=google_auth_failed")
    try:
        exchange_code(code)
    except Exception as exc:
        return RedirectResponse(f"/?error=google_auth_failed&detail={exc}")
    return RedirectResponse("/?connected=1")


@router.delete("/api/google/disconnect")
async def google_disconnect(_: str = Depends(require_auth)):
    revoke_credentials()
    return {"message": "Google account disconnected"}
