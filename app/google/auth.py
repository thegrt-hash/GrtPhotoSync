"""Google OAuth2 flow – token acquisition, storage, and refresh."""

import json
import os
import logging
from typing import Optional

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import Flow

from app.config import settings

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/photoslibrary.readonly",
]

TOKEN_FILE = settings.GOOGLE_TOKEN_FILE


def _client_config() -> dict:
    """Build the OAuth client config dict from environment variables."""
    return {
        "web": {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uris": [settings.GOOGLE_REDIRECT_URI],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }


def get_auth_url() -> tuple[str, str]:
    """Return (authorization_url, state) to redirect the user to Google."""
    flow = Flow.from_client_config(
        _client_config(),
        scopes=SCOPES,
        redirect_uri=settings.GOOGLE_REDIRECT_URI,
    )
    flow.code_challenge_method = None  # PKCE not used in server-side flow
    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    return auth_url, state


def exchange_code(code: str) -> Credentials:
    """Exchange an authorization code for credentials and persist them."""
    flow = Flow.from_client_config(
        _client_config(),
        scopes=SCOPES,
        redirect_uri=settings.GOOGLE_REDIRECT_URI,
    )
    flow.fetch_token(code=code)
    creds = flow.credentials
    _save_token(creds)
    return creds


def load_credentials() -> Optional[Credentials]:
    """Load stored credentials, refreshing them if expired."""
    if not os.path.exists(TOKEN_FILE):
        return None

    try:
        with open(TOKEN_FILE, "r") as f:
            data = json.load(f)

        creds = Credentials(
            token=data.get("token"),
            refresh_token=data.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.GOOGLE_CLIENT_ID,
            client_secret=settings.GOOGLE_CLIENT_SECRET,
            scopes=SCOPES,
        )

        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            _save_token(creds)

        return creds if creds.valid else None

    except Exception as exc:
        logger.warning("Failed to load Google credentials: %s", exc)
        return None


def revoke_credentials() -> None:
    """Delete the stored token file."""
    if os.path.exists(TOKEN_FILE):
        os.remove(TOKEN_FILE)
        logger.info("Google credentials revoked")


def is_connected() -> bool:
    return load_credentials() is not None


def _save_token(creds: Credentials) -> None:
    os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
    with open(TOKEN_FILE, "w") as f:
        json.dump(
            {
                "token": creds.token,
                "refresh_token": creds.refresh_token,
                "token_uri": creds.token_uri,
                "scopes": list(creds.scopes or []),
            },
            f,
            indent=2,
        )
    logger.debug("Google token saved to %s", TOKEN_FILE)
