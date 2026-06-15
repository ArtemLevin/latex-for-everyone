import json
import logging
import time
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path

from app.config import settings
from app.services.artifact_paths import artifact_cleanup_policies, ensure_trusted_artifact_root

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ArtifactCleanupReport:
    root_name: str
    root: str
    dry_run: bool
    deleted_files: int = 0
    would_delete_files: int = 0
    skipped_files: int = 0
    error_count: int = 0
    deleted_bytes: int = 0
    would_delete_bytes: int = 0
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _iter_cleanup_files(cleanup_dir: Path, *, recursive: bool) -> Iterable[Path]:
    return cleanup_dir.rglob("*") if recursive else cleanup_dir.iterdir()


def cleanup_old_files_report(
    directory: Path,
    *,
    max_age_seconds: int,
    suffixes: Iterable[str] | None = None,
    trusted_roots: tuple[Path, ...] | None = None,
    recursive: bool = False,
    dry_run: bool = False,
    root_name: str = "custom",
) -> ArtifactCleanupReport:
    """Safely inspect/delete old artifact files under one trusted root.

    The function deliberately keeps dry-run and commit paths identical until the
    final `unlink()` call, so operators can trust the reported candidate set
    before scheduling destructive cleanup in production.
    """
    started = time.perf_counter()
    if max_age_seconds <= 0:
        return ArtifactCleanupReport(root_name=root_name, root=str(directory), dry_run=dry_run)

    cleanup_dir = ensure_trusted_artifact_root(directory, trusted_roots) if trusted_roots is not None else directory.resolve()
    if not cleanup_dir.exists():
        return ArtifactCleanupReport(root_name=root_name, root=str(cleanup_dir), dry_run=dry_run)

    allowed_suffixes = {suffix.lower() for suffix in suffixes} if suffixes else None
    cutoff = time.time() - max_age_seconds
    deleted = 0
    would_delete = 0
    skipped = 0
    errors = 0
    deleted_bytes = 0
    would_delete_bytes = 0

    for path in _iter_cleanup_files(cleanup_dir, recursive=recursive):
        try:
            if not path.is_file() or path.is_symlink():
                skipped += 1
                continue
            if allowed_suffixes is not None and path.suffix.lower() not in allowed_suffixes:
                skipped += 1
                continue
            stat = path.stat()
            if stat.st_mtime >= cutoff:
                skipped += 1
                continue
            if dry_run:
                would_delete += 1
                would_delete_bytes += stat.st_size
                continue
            path.unlink()
            deleted += 1
            deleted_bytes += stat.st_size
        except OSError:
            errors += 1

    duration_ms = (time.perf_counter() - started) * 1000
    report = ArtifactCleanupReport(
        root_name=root_name,
        root=str(cleanup_dir),
        dry_run=dry_run,
        deleted_files=deleted,
        would_delete_files=would_delete,
        skipped_files=skipped,
        error_count=errors,
        deleted_bytes=deleted_bytes,
        would_delete_bytes=would_delete_bytes,
        duration_ms=round(duration_ms, 2),
    )
    logger.info("artifact cleanup completed report=%s", json.dumps(report.to_dict(), ensure_ascii=False, sort_keys=True))
    return report


def cleanup_old_files(
    directory: Path,
    *,
    max_age_seconds: int,
    suffixes: Iterable[str] | None = None,
    trusted_roots: tuple[Path, ...] | None = None,
) -> int:
    """Delete old artifact files from a directory and return the number removed."""
    return cleanup_old_files_report(
        directory,
        max_age_seconds=max_age_seconds,
        suffixes=suffixes,
        trusted_roots=trusted_roots,
    ).deleted_files


def cleanup_configured_artifacts(*, dry_run: bool = True, max_age_seconds: int | None = None) -> list[ArtifactCleanupReport]:
    ttl = settings.ARTIFACT_TTL_SECONDS if max_age_seconds is None else max_age_seconds
    policies = artifact_cleanup_policies()
    trusted_roots = tuple(policy.root for policy in policies)
    return [
        cleanup_old_files_report(
            policy.root,
            root_name=policy.name,
            max_age_seconds=ttl,
            suffixes=policy.suffixes,
            trusted_roots=trusted_roots,
            recursive=policy.recursive,
            dry_run=dry_run,
        )
        for policy in policies
    ]
