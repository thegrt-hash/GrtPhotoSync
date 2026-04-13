"""Throttled, resumable async file downloader.

Features
────────
- Token-bucket rate limiting (speed in MB/s, 0 = unlimited)
- Resume via HTTP Range requests – partial downloads stored as <path>.part
- Exponential-backoff retry on network errors
- Progress callback so the manager can track bytes transferred
"""

import asyncio
import logging
import os
from typing import Callable, Optional

import aiohttp

from app.config import settings

logger = logging.getLogger(__name__)

CHUNK = settings.CHUNK_SIZE          # bytes per read iteration
MAX_RETRIES = settings.MAX_RETRIES


# ── Token bucket ──────────────────────────────────────────────────────────────

class TokenBucket:
    """Thread-safe token bucket for bandwidth throttling."""

    def __init__(self, rate_bytes_per_sec: float):
        self.rate = rate_bytes_per_sec          # 0 means unlimited
        self.tokens = rate_bytes_per_sec
        self._last = asyncio.get_event_loop().time() if rate_bytes_per_sec > 0 else 0
        self._lock = asyncio.Lock()

    async def consume(self, nbytes: int) -> None:
        if self.rate <= 0:
            return
        async with self._lock:
            now = asyncio.get_event_loop().time()
            elapsed = now - self._last
            self.tokens = min(self.rate, self.tokens + elapsed * self.rate)
            self._last = now

            if self.tokens < nbytes:
                wait = (nbytes - self.tokens) / self.rate
                await asyncio.sleep(wait)
                self.tokens = 0
            else:
                self.tokens -= nbytes

    def update_rate(self, mbps: float) -> None:
        self.rate = mbps * 1024 * 1024
        if self.rate > 0:
            self.tokens = min(self.tokens, self.rate)


# Singleton bucket – updated when settings change
_bucket: Optional[TokenBucket] = None


def get_bucket() -> TokenBucket:
    global _bucket
    if _bucket is None:
        rate = settings.SPEED_LIMIT_MBPS * 1024 * 1024
        _bucket = TokenBucket(rate)
    return _bucket


def update_speed_limit(mbps: float) -> None:
    get_bucket().update_rate(mbps)


# ── Downloader ────────────────────────────────────────────────────────────────

async def download_file(
    url: str,
    dest_path: str,
    *,
    on_progress: Optional[Callable[[int], None]] = None,
) -> int:
    """Download *url* to *dest_path*, resuming any partial download.

    Returns the total bytes written in this call.

    Raises RuntimeError if all retries are exhausted.
    """
    part_path = dest_path + ".part"
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)

    bucket = get_bucket()
    bytes_written = 0

    for attempt in range(1, MAX_RETRIES + 1):
        # How many bytes do we already have?
        resume_from = os.path.getsize(part_path) if os.path.exists(part_path) else 0

        headers = {}
        if resume_from > 0:
            headers["Range"] = f"bytes={resume_from}-"
            logger.debug("Resuming %s from byte %d", dest_path, resume_from)

        try:
            timeout = aiohttp.ClientTimeout(total=300, connect=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, headers=headers) as resp:
                    if resp.status == 416:
                        # Server says range not satisfiable → file already complete
                        logger.debug("Server 416 – file already complete: %s", dest_path)
                        _finalise(part_path, dest_path)
                        return 0

                    if resp.status not in (200, 206):
                        raise aiohttp.ClientResponseError(
                            resp.request_info, resp.history, status=resp.status
                        )

                    mode = "ab" if resume_from > 0 and resp.status == 206 else "wb"
                    with open(part_path, mode) as fh:
                        async for chunk in resp.content.iter_chunked(CHUNK):
                            await bucket.consume(len(chunk))
                            fh.write(chunk)
                            bytes_written += len(chunk)
                            if on_progress:
                                on_progress(len(chunk))

            _finalise(part_path, dest_path)
            return bytes_written

        except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as exc:
            delay = 2.0 * (2 ** (attempt - 1))
            logger.warning(
                "Download attempt %d/%d failed (%s) → retry in %.1fs",
                attempt, MAX_RETRIES, exc, delay
            )
            if attempt < MAX_RETRIES:
                await asyncio.sleep(delay)

    raise RuntimeError(f"Failed to download after {MAX_RETRIES} attempts: {url}")


def _finalise(part_path: str, dest_path: str) -> None:
    """Atomically rename .part → final destination."""
    if os.path.exists(part_path):
        os.replace(part_path, dest_path)
        logger.debug("Download complete: %s", dest_path)
