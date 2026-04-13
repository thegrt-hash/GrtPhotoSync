"""Thumbnail generation and EXIF metadata utilities for local files."""

import asyncio
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

THUMBNAIL_SIZE = (256, 256)
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".3gp"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".tiff", ".bmp"}


def generate_thumbnail(src_path: str, thumb_path: str, size: tuple = THUMBNAIL_SIZE) -> bool:
    """Generate a JPEG thumbnail and save it to thumb_path.

    Returns True on success, False on failure (e.g., video files where Pillow
    can't generate a frame thumbnail without ffmpeg).
    """
    try:
        from PIL import Image, UnidentifiedImageError  # local import so the app starts without PIL

        os.makedirs(os.path.dirname(thumb_path), exist_ok=True)
        with Image.open(src_path) as img:
            img.thumbnail(size, Image.LANCZOS)
            img = img.convert("RGB")   # normalise to JPEG-safe mode
            img.save(thumb_path, "JPEG", quality=75, optimize=True)
        return True
    except Exception as exc:
        logger.debug("Thumbnail generation failed for %s: %s", src_path, exc)
        return False


def get_cached_thumbnail(src_path: str, cache_dir: str) -> Optional[str]:
    """Return the cached thumbnail path if it exists and is newer than the source."""
    rel = os.path.relpath(src_path, "/")   # strip leading slash for safe path
    thumb_path = os.path.join(cache_dir, rel + ".thumb.jpg")

    if os.path.exists(thumb_path):
        if os.path.getmtime(thumb_path) >= os.path.getmtime(src_path):
            return thumb_path

    if generate_thumbnail(src_path, thumb_path):
        return thumb_path
    return None


def read_exif_location(path: str) -> tuple[Optional[float], Optional[float]]:
    """Read GPS coordinates from a JPEG's EXIF data.

    Returns (latitude, longitude) or (None, None).
    """
    ext = os.path.splitext(path)[1].lower()
    if ext not in (".jpg", ".jpeg", ".tiff"):
        return None, None

    try:
        import piexif

        exif = piexif.load(path)
        gps = exif.get("GPS", {})
        if not gps:
            return None, None

        def _dms_to_decimal(dms, ref):
            d = dms[0][0] / dms[0][1]
            m = dms[1][0] / dms[1][1] / 60
            s = dms[2][0] / dms[2][1] / 3600
            val = d + m + s
            if ref in (b"S", b"W"):
                val = -val
            return val

        lat = _dms_to_decimal(gps[piexif.GPSIFD.GPSLatitude], gps[piexif.GPSIFD.GPSLatitudeRef])
        lon = _dms_to_decimal(gps[piexif.GPSIFD.GPSLongitude], gps[piexif.GPSIFD.GPSLongitudeRef])
        return lat, lon
    except Exception:
        return None, None


async def generate_thumbnail_async(src_path: str, thumb_path: str) -> bool:
    """Run thumbnail generation in a thread pool (non-blocking)."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, generate_thumbnail, src_path, thumb_path)
