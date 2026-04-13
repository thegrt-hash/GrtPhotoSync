"""Authentication router – login / logout / session check."""

from fastapi import APIRouter, HTTPException, Response, Request, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional

from app.config import settings
from app.auth.utils import verify_password, create_access_token, decode_token, hash_password

router = APIRouter(prefix="/api/auth", tags=["auth"])
bearer = HTTPBearer(auto_error=False)

COOKIE_NAME = "gpd_token"


# ── Schemas ───────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str
    timeout_minutes: Optional[int] = None   # 15 | 60 | 1440 | 10080


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


# ── Dependency ────────────────────────────────────────────────────────────────

def _extract_token(request: Request) -> Optional[str]:
    """Read token from cookie first, then Authorization header."""
    token = request.cookies.get(COOKIE_NAME)
    if token:
        return token
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


def require_auth(request: Request) -> str:
    """FastAPI dependency that returns the username or raises 401."""
    token = _extract_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    username = decode_token(token)
    if not username:
        raise HTTPException(status_code=401, detail="Session expired or invalid")
    return username


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/login")
async def login(body: LoginRequest, response: Response):
    # Validate credentials against env-configured values
    if body.username != settings.WEB_USERNAME or not verify_password(body.password, hash_password(settings.WEB_PASSWORD)):
        # Direct comparison as fallback (plain password in .env)
        if body.username != settings.WEB_USERNAME or body.password != settings.WEB_PASSWORD:
            raise HTTPException(status_code=401, detail="Invalid credentials")

    allowed = {15, 60, 1440, 10080}
    timeout = body.timeout_minutes if body.timeout_minutes in allowed else settings.SESSION_TIMEOUT_MINUTES
    token = create_access_token(body.username, expires_minutes=timeout)

    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=timeout * 60,
        secure=False,   # Set True if using HTTPS
    )
    return {"message": "Login successful", "timeout_minutes": timeout}


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(COOKIE_NAME)
    return {"message": "Logged out"}


@router.get("/status")
async def auth_status(username: str = Depends(require_auth)):
    return {
        "authenticated": True,
        "username": username,
        "session_timeout_minutes": settings.SESSION_TIMEOUT_MINUTES,
    }


@router.put("/settings")
async def update_auth_settings(
    body: ChangePasswordRequest,
    username: str = Depends(require_auth),
):
    """Allow the admin to change their own password."""
    if body.current_password != settings.WEB_PASSWORD:
        raise HTTPException(status_code=403, detail="Current password incorrect")
    # NOTE: In a multi-user future this would update the DB.
    # For now, remind the user to update their .env file.
    return {
        "message": "To permanently change password, update WEB_PASSWORD in your .env file and restart.",
        "new_password_preview": body.new_password[:2] + "****",
    }
