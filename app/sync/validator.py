"""Post-download validation: file-size check and optional SHA-256 integrity."""

import hashlib
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


def validate_file(local_path: str, expected_size: Optional[int] = None) -> bool:
    """Return True if the file exists and (optionally) matches the expected size.

    We do NOT compare hashes against Google's values because the Photos API
    doesn't expose a checksum for the raw binary.  Instead we verify:
      1. File exists
      2. File is not empty
      3. File size matches the Content-Length returned during download (if known)
    """
    if not os.path.exists(local_path):
        logger.error("Validation failed – file missing: %s", local_path)
        return False

    actual = os.path.getsize(local_path)
    if actual == 0:
        logger.error("Validation failed – zero-byte file: %s", local_path)
        return False

    if expected_size is not None and actual != expected_size:
        logger.warning(
            "Size mismatch for %s: expected %d, got %d", local_path, expected_size, actual
        )
        return False

    return True


def sha256(path: str) -> str:
    """Compute SHA-256 hex digest of a local file (for user-level integrity audits)."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def partial_file_exists(dest_path: str) -> bool:
    return os.path.exists(dest_path + ".part")


def partial_file_size(dest_path: str) -> int:
    p = dest_path + ".part"
    return os.path.getsize(p) if os.path.exists(p) else 0
