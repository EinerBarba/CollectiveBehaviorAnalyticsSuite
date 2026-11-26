"""Local file storage.

Files are written under `<storage_root>/local/`. The database stores only each
file's storage key (its path relative to that folder), its size and its
SHA-256 checksum. See [Storage](../storage.md).
"""

import hashlib
import uuid
from pathlib import Path

from app.config import settings

STORAGE_BUCKET = "local"
"""Name of the storage folder under `storage_root`, also recorded on every file version."""


def full_path(storage_key: str) -> Path:
    """Turn a storage key into an absolute path on disk.

    Args:
        storage_key: Path relative to the storage bucket, as stored on a
            file version.

    Returns:
        The resolved absolute path.

    Raises:
        ValueError: If the key would resolve outside the storage root, for
            example through `..` segments.
    """
    root = Path(settings.storage_root).resolve()
    path = (root / STORAGE_BUCKET / storage_key).resolve()
    if root not in path.parents:
        raise ValueError("Invalid storage path")
    return path


def save_bytes(data: bytes, subdir: str, filename: str) -> tuple[str, str, int]:
    """Write bytes to storage under a unique name.

    A random prefix is added to the file name, so saving the same name twice
    never overwrites an earlier file.

    Args:
        data: The file contents.
        subdir: Folder within the bucket, for example
            `experiments/<id>/processing-runs/<id>`.
        filename: Human-readable file name to keep after the random prefix.

    Returns:
        The storage key, the SHA-256 checksum as hex, and the size in bytes.
    """
    checksum = hashlib.sha256(data).hexdigest()
    key = f"{subdir}/{uuid.uuid4().hex}_{filename}"
    path = full_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return key, checksum, len(data)
