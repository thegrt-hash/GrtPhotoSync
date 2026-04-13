"""Async Google Photos Library API client with pagination, rate-limit backoff,
and original-quality download URL construction."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import AsyncIterator, Optional
from urllib.parse import urlencode

import httpx

from app.google.auth import load_credentials

logger = logging.getLogger(__name__)

BASE_URL = "https://photoslibrary.googleapis.com/v1"
MAX_PAGE_SIZE = 100          # Google's maximum
RETRY_ATTEMPTS = 5
RETRY_BASE_DELAY = 2.0       # seconds


def _auth_headers() -> dict:
    creds = load_credentials()
    if not creds or not creds.token:
        raise RuntimeError("Google account not connected. Please authenticate first.")
    return {"Authorization": f"Bearer {creds.token}", "Content-Type": "application/json"}


async def _get(client: httpx.AsyncClient, url: str, params: dict | None = None) -> dict:
    """HTTP GET with exponential-backoff retry for 429 / 5xx."""
    for attempt in range(RETRY_ATTEMPTS):
        try:
            resp = await client.get(url, params=params, headers=_auth_headers(), timeout=30)
            if resp.status_code == 429 or resp.status_code >= 500:
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning("API %s %s → retrying in %.1fs", resp.status_code, url, delay)
                await asyncio.sleep(delay)
                continue
            resp.raise_for_status()
            return resp.json()
        except httpx.TransportError as exc:
            delay = RETRY_BASE_DELAY * (2 ** attempt)
            logger.warning("Network error %s → retrying in %.1fs: %s", url, delay, exc)
            await asyncio.sleep(delay)
    raise RuntimeError(f"Exhausted {RETRY_ATTEMPTS} retries for {url}")


async def _post(client: httpx.AsyncClient, url: str, body: dict) -> dict:
    """HTTP POST with retry."""
    for attempt in range(RETRY_ATTEMPTS):
        try:
            resp = await client.post(url, json=body, headers=_auth_headers(), timeout=30)
            if resp.status_code == 429 or resp.status_code >= 500:
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                await asyncio.sleep(delay)
                continue
            resp.raise_for_status()
            return resp.json()
        except httpx.TransportError as exc:
            delay = RETRY_BASE_DELAY * (2 ** attempt)
            await asyncio.sleep(delay)
    raise RuntimeError(f"Exhausted {RETRY_ATTEMPTS} retries for POST {url}")


# ── Media Items ───────────────────────────────────────────────────────────────

async def iter_all_media_items(
    after: Optional[datetime] = None,
) -> AsyncIterator[dict]:
    """Yield every media item in the library, newest-first.

    Args:
        after: If provided, only yield items created on or after this time.
    """
    async with httpx.AsyncClient() as client:
        page_token: Optional[str] = None
        while True:
            body: dict = {"pageSize": MAX_PAGE_SIZE}
            if page_token:
                body["pageToken"] = page_token
            if after:
                body["filters"] = {
                    "dateFilter": {
                        "ranges": [
                            {
                                "startDate": {
                                    "year": after.year,
                                    "month": after.month,
                                    "day": after.day,
                                }
                            }
                        ]
                    }
                }

            data = await _post(client, f"{BASE_URL}/mediaItems:search", body)
            items = data.get("mediaItems", [])
            for item in items:
                yield item

            page_token = data.get("nextPageToken")
            if not page_token:
                break


async def get_media_item(media_id: str) -> dict:
    """Fetch a single media item (refreshes its baseUrl)."""
    async with httpx.AsyncClient() as client:
        return await _get(client, f"{BASE_URL}/mediaItems/{media_id}")


async def iter_all_albums() -> AsyncIterator[dict]:
    """Yield every album in the library."""
    async with httpx.AsyncClient() as client:
        page_token: Optional[str] = None
        while True:
            params = {"pageSize": 50}
            if page_token:
                params["pageToken"] = page_token
            data = await _get(client, f"{BASE_URL}/albums", params=params)
            for album in data.get("albums", []):
                yield album
            page_token = data.get("nextPageToken")
            if not page_token:
                break


async def iter_album_items(album_id: str) -> AsyncIterator[dict]:
    """Yield every media item in a specific album."""
    async with httpx.AsyncClient() as client:
        page_token: Optional[str] = None
        while True:
            body: dict = {"albumId": album_id, "pageSize": MAX_PAGE_SIZE}
            if page_token:
                body["pageToken"] = page_token
            data = await _post(client, f"{BASE_URL}/mediaItems:search", body)
            for item in data.get("mediaItems", []):
                yield item
            page_token = data.get("nextPageToken")
            if not page_token:
                break


# ── Download URL helpers ───────────────────────────────────────────────────────

def photo_download_url(base_url: str) -> str:
    """Original-quality photo download URL."""
    return f"{base_url}=d"


def video_download_url(base_url: str) -> str:
    """Original-quality video download URL."""
    return f"{base_url}=dv"


def thumbnail_url(base_url: str, width: int = 256, height: int = 256) -> str:
    """Thumbnail URL for browsing (not downloaded to disk)."""
    return f"{base_url}=w{width}-h{height}-c"


# ── Metadata helpers ───────────────────────────────────────────────────────────

def parse_creation_time(item: dict) -> Optional[datetime]:
    raw = item.get("mediaMetadata", {}).get("creationTime")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def is_video(item: dict) -> bool:
    return "video" in item.get("mediaMetadata", {})


def extract_location(item: dict) -> tuple[Optional[float], Optional[float]]:
    """Return (latitude, longitude) from the media item if available."""
    photo_meta = item.get("mediaMetadata", {}).get("photo", {})
    lat = photo_meta.get("latitude")
    lon = photo_meta.get("longitude")
    if lat is not None:
        return float(lat), float(lon)
    return None, None


async def list_media_items_page(page_token: Optional[str] = None, page_size: int = 50) -> dict:
    """Return a single page of media items (for the browser UI)."""
    async with httpx.AsyncClient() as client:
        body: dict = {"pageSize": min(page_size, MAX_PAGE_SIZE)}
        if page_token:
            body["pageToken"] = page_token
        return await _post(client, f"{BASE_URL}/mediaItems:search", body)
