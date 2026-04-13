"""Settings API – read and update runtime configuration."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.auth.router import require_auth
from app.config import settings
from app.sync.transfer import update_speed_limit
from app.sync.scheduler import update_interval

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsResponse(BaseModel):
    speed_limit_mbps: float
    sync_interval_minutes: int
    max_retries: int
    chunk_size: int
    destination_path: str
    session_timeout_minutes: int
    google_redirect_uri: str


class SettingsUpdate(BaseModel):
    speed_limit_mbps: Optional[float] = None
    sync_interval_minutes: Optional[int] = None
    session_timeout_minutes: Optional[int] = None


@router.get("", response_model=SettingsResponse)
async def get_settings(_: str = Depends(require_auth)):
    return SettingsResponse(
        speed_limit_mbps=settings.SPEED_LIMIT_MBPS,
        sync_interval_minutes=settings.SYNC_INTERVAL_MINUTES,
        max_retries=settings.MAX_RETRIES,
        chunk_size=settings.CHUNK_SIZE,
        destination_path=settings.DESTINATION_PATH,
        session_timeout_minutes=settings.SESSION_TIMEOUT_MINUTES,
        google_redirect_uri=settings.GOOGLE_REDIRECT_URI,
    )


@router.put("")
async def update_settings(body: SettingsUpdate, _: str = Depends(require_auth)):
    """Update runtime settings (persisted only until container restart unless .env is updated)."""
    changed = {}

    if body.speed_limit_mbps is not None:
        if body.speed_limit_mbps < 0:
            raise HTTPException(400, "Speed limit cannot be negative")
        settings.SPEED_LIMIT_MBPS = body.speed_limit_mbps
        update_speed_limit(body.speed_limit_mbps)
        changed["speed_limit_mbps"] = body.speed_limit_mbps

    if body.sync_interval_minutes is not None:
        if body.sync_interval_minutes < 5:
            raise HTTPException(400, "Sync interval must be at least 5 minutes")
        settings.SYNC_INTERVAL_MINUTES = body.sync_interval_minutes
        update_interval(body.sync_interval_minutes)
        changed["sync_interval_minutes"] = body.sync_interval_minutes

    if body.session_timeout_minutes is not None:
        allowed = {15, 60, 1440, 10080}
        if body.session_timeout_minutes not in allowed:
            raise HTTPException(400, f"Session timeout must be one of {allowed}")
        settings.SESSION_TIMEOUT_MINUTES = body.session_timeout_minutes
        changed["session_timeout_minutes"] = body.session_timeout_minutes

    return {"updated": changed, "note": "Update your .env file to make changes permanent."}
