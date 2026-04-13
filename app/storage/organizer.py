"""File-system layout rules for the destination directory.

Folder layout
─────────────
  {dest}/
    2024/
      01 - January/
        photo.jpg
        video.mp4
      02 - February/
        ...
    Albums/
      My Vacation/         ← symlinks → ../../../2024/01/photo.jpg
        photo.jpg -> ...
"""

import logging
import os
import re
from typing import Optional

MONTH_NAMES = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

logger = logging.getLogger(__name__)


def year_month_dir(dest: str, year: int, month: int) -> str:
    month_label = f"{month:02d} - {MONTH_NAMES[month]}"
    return os.path.join(dest, str(year), month_label)


def resolve_local_path(media, dest: str) -> str:
    """Compute the absolute destination path for a MediaItem ORM object.

    Falls back to a root-level 'Unknown' folder when date is unavailable.
    Handles filename collisions by appending a counter suffix.
    """
    if media.year and media.month:
        directory = year_month_dir(dest, media.year, media.month)
    else:
        directory = os.path.join(dest, "Unknown")

    os.makedirs(directory, exist_ok=True)
    base, ext = os.path.splitext(media.filename)

    candidate = os.path.join(directory, media.filename)
    if not os.path.exists(candidate):
        return candidate

    # Collision: append _2, _3, …
    counter = 2
    while True:
        candidate = os.path.join(directory, f"{base}_{counter}{ext}")
        if not os.path.exists(candidate):
            return candidate
        counter += 1


def ensure_album_link(
    source_path: str,
    album_title: str,
    dest: str,
    filename: str,
) -> None:
    """Create a symlink inside Albums/{album_title}/ pointing to source_path."""
    safe_title = _safe_dirname(album_title)
    album_dir = os.path.join(dest, "Albums", safe_title)
    os.makedirs(album_dir, exist_ok=True)

    link_path = os.path.join(album_dir, filename)
    if os.path.islink(link_path) or os.path.exists(link_path):
        return

    try:
        rel_target = os.path.relpath(source_path, album_dir)
        os.symlink(rel_target, link_path)
    except OSError as exc:
        logger.warning("Could not create album symlink %s → %s: %s", link_path, source_path, exc)


def _safe_dirname(name: str) -> str:
    """Strip / replace characters unsafe for directory names."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    return name.strip(". ") or "Untitled"


def list_local_files(base: str, year: Optional[int] = None, month: Optional[int] = None):
    """Yield (relative_path, abs_path, size) tuples for local photo files."""
    if year and month:
        root = year_month_dir(base, year, month)
    elif year:
        root = os.path.join(base, str(year))
    else:
        root = base

    if not os.path.isdir(root):
        return

    extensions = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".mp4", ".mov", ".avi", ".mkv", ".heic"}
    for dirpath, _, filenames in os.walk(root):
        for fname in sorted(filenames):
            if os.path.splitext(fname)[1].lower() in extensions:
                abs_path = os.path.join(dirpath, fname)
                rel_path = os.path.relpath(abs_path, base)
                yield rel_path, abs_path, os.path.getsize(abs_path)
