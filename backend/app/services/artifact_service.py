import hashlib
import re
import shutil
import uuid
from datetime import UTC, timedelta
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Artifact
from app.services.artifact_paths import ArtifactDownloadTarget, ArtifactKind, resolve_artifact_download
from app.time_utils import utc_now

ArtifactFormat = Literal["pdf", "html", "tex_zip"]
ArtifactStorageRoot = Literal["compile_pdf", "export"]

FORMAT_SUFFIXES: dict[str, str] = {
    "pdf": ".pdf",
    "html": ".html",
    "tex_zip": ".zip",
}


class ArtifactNotFoundError(Exception):
    """Raised when an artifact record is not visible to the owner."""


class ArtifactExpiredError(Exception):
    """Raised when an artifact exists but is no longer downloadable."""


class ArtifactMissingFileError(Exception):
    """Raised when an artifact record points to a missing file."""


class ArtifactCreationError(Exception):
    """Raised when an artifact record cannot be created safely."""


@dataclass(frozen=True)
class CreatedArtifact:
    id: str
    download_url: str
    original_filename: str
    storage_filename: str
    size_bytes: int
    media_type: str


@dataclass(frozen=True)
class AuthorizedArtifactDownload:
    artifact: Artifact
    target: ArtifactDownloadTarget


def make_storage_filename(format: ArtifactFormat) -> str:
    suffix = FORMAT_SUFFIXES[format]
    return f"artifact_{uuid.uuid4().hex}{suffix}"


def safe_original_filename(filename: str, *, fallback_stem: str = "artifact", format: ArtifactFormat = "pdf") -> str:
    suffix = FORMAT_SUFFIXES[format]
    candidate = Path(filename or "").name.strip()
    if not candidate:
        candidate = f"{fallback_stem}{suffix}"
    stem = Path(candidate).stem or fallback_stem
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-") or fallback_stem
    return f"{safe_stem[:120]}{suffix}"


def _download_url(artifact_id: str) -> str:
    return f"/api/artifacts/{artifact_id}/download"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _expires_at(ttl_seconds: int | None):
    ttl = settings.ARTIFACT_TTL_SECONDS if ttl_seconds is None else ttl_seconds
    return utc_now() + timedelta(seconds=ttl)


def create_artifact_record(
    db: Session,
    *,
    owner_id: str,
    kind: ArtifactKind,
    format: ArtifactFormat,
    storage_root: ArtifactStorageRoot,
    source_path: Path,
    original_filename: str,
    project_id: str | None = None,
    compile_history_id: str | None = None,
    content_disposition_type: str | None = None,
    ttl_seconds: int | None = None,
) -> CreatedArtifact:
    if not source_path.is_file():
        raise ArtifactCreationError("Artifact source file does not exist")

    storage_filename = make_storage_filename(format)
    target = resolve_artifact_download(storage_root, storage_filename)
    target.path.parent.mkdir(parents=True, exist_ok=True)

    moved = False
    try:
        if source_path.resolve() != target.path.resolve():
            shutil.move(str(source_path), str(target.path))
            moved = True

        size_bytes = target.path.stat().st_size
        checksum = _sha256(target.path)
        artifact = Artifact(
            owner_id=owner_id,
            project_id=project_id,
            compile_history_id=compile_history_id,
            kind=kind,
            format=format,
            original_filename=safe_original_filename(original_filename, format=format),
            storage_filename=target.filename,
            storage_root=storage_root,
            media_type=target.media_type,
            content_disposition_type=content_disposition_type or target.content_disposition_type,
            size_bytes=size_bytes,
            sha256_checksum=checksum,
            status="available",
            expires_at=_expires_at(ttl_seconds),
            created_at=utc_now(),
            access_count=0,
        )
        db.add(artifact)
        db.flush()
        return CreatedArtifact(
            id=artifact.id,
            download_url=_download_url(artifact.id),
            original_filename=artifact.original_filename,
            storage_filename=artifact.storage_filename,
            size_bytes=size_bytes,
            media_type=artifact.media_type,
        )
    except Exception:
        if moved and target.path.exists():
            target.path.unlink()
        raise


def _authorized_query(db: Session, *, owner_id: str):
    return db.query(Artifact).filter(Artifact.owner_id == owner_id)


def _validate_available_artifact(artifact: Artifact) -> ArtifactDownloadTarget:
    now = utc_now()
    expires_at = artifact.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if artifact.status == "expired" or expires_at <= now:
        artifact.status = "expired"
        raise ArtifactExpiredError("Artifact expired")
    if artifact.status != "available":
        raise ArtifactNotFoundError("Artifact not available")

    target = resolve_artifact_download(artifact.storage_root, artifact.storage_filename)
    if not target.path.is_file():
        artifact.status = "deleted"
        raise ArtifactMissingFileError("Artifact file not found")
    return target


def get_authorized_artifact_download(db: Session, *, artifact_id: str, owner_id: str) -> AuthorizedArtifactDownload:
    artifact = _authorized_query(db, owner_id=owner_id).filter(Artifact.id == artifact_id).first()
    if artifact is None:
        raise ArtifactNotFoundError("Artifact not found")
    target = _validate_available_artifact(artifact)
    return AuthorizedArtifactDownload(artifact=artifact, target=target)


def find_authorized_artifact_by_storage_filename(
    db: Session,
    *,
    owner_id: str,
    kind: ArtifactKind,
    storage_filename: str,
) -> AuthorizedArtifactDownload:
    artifact = (
        _authorized_query(db, owner_id=owner_id)
        .filter(Artifact.kind == kind, Artifact.storage_filename == storage_filename)
        .first()
    )
    if artifact is None:
        raise ArtifactNotFoundError("Artifact not found")
    target = _validate_available_artifact(artifact)
    return AuthorizedArtifactDownload(artifact=artifact, target=target)


def mark_artifact_accessed(db: Session, *, artifact: Artifact) -> None:
    artifact.accessed_at = utc_now()
    artifact.access_count = (artifact.access_count or 0) + 1
    db.add(artifact)
    db.commit()
