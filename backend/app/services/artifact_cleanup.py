import time
from pathlib import Path
from collections.abc import Iterable

from app.services.artifact_paths import ensure_trusted_artifact_root


def cleanup_old_files(
    directory: Path,
    *,
    max_age_seconds: int,
    suffixes: Iterable[str] | None = None,
    trusted_roots: tuple[Path, ...] | None = None,
) -> int:
    """Delete old artifact files from a directory and return the number removed.

    When trusted_roots is provided, the cleanup directory must resolve exactly to
    one of those roots. This keeps production artifact cleanup from accidentally
    deleting files outside configured runtime artifact directories.
    """
    if max_age_seconds <= 0:
        return 0

    cleanup_dir = ensure_trusted_artifact_root(directory, trusted_roots) if trusted_roots is not None else directory
    if not cleanup_dir.exists():
        return 0

    allowed_suffixes = {suffix.lower() for suffix in suffixes} if suffixes else None
    cutoff = time.time() - max_age_seconds
    removed = 0

    for path in cleanup_dir.iterdir():
        if not path.is_file() or path.is_symlink():
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
