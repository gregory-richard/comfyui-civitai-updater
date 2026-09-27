from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Callable


class HashingCancelled(Exception):
    """Raised when ``should_stop`` asks to abandon a hash midway."""


def sha256_file(
    file_path: Path,
    chunk_size: int = 1024 * 1024,
    should_stop: Callable[[], bool] | None = None,
) -> str:
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        while True:
            # A checkpoint takes minutes to hash; Stop must not wait for it.
            if should_stop and should_stop():
                raise HashingCancelled(str(file_path))
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()

