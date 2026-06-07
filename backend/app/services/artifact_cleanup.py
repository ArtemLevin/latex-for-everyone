import time
from pathlib import Path
from collections.abc import Iterable


def cleanup_old_files(directory: Path, *, max_age_seconds: int, suffixes: Iterable[str] | None = None) -> int:
    """Delete old artifact files from a directory and return the number removed."""
    if max_age_seconds <= 0 or not directory.exists():
        return 0

    allowed_suffixes = {suffix.lower() for suffix in suffixes} if suffixes else None
    cutoff = time.time() - max_age_seconds
    removed = 0

    for path in directory.iterdir():
        if not path.is_file():
            continue
        if allowed_suffixes is not None and path.suffix.lower() not in allowed_suffixes:
            continue
        try:
            if path.stat().st_mtime >= cutoff:
                continue
            path.unlink()
            removed += 1
        except OSError:
            continue
    return removed
