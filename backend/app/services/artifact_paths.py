from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.config import settings

ArtifactKind = Literal["compile_pdf", "export"]

EXPORT_MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".html": "text/html",
    ".zip": "application/zip",
}
COMPILE_MEDIA_TYPES = {
    ".pdf": "application/pdf",
}


class ArtifactPathError(Exception):
    """Base error for unsafe or unsupported artifact paths."""


class InvalidArtifactFilenameError(ArtifactPathError):
    """Raised when an artifact filename is unsafe."""


class UnsupportedArtifactTypeError(ArtifactPathError):
    """Raised when an artifact suffix is not downloadable for the artifact kind."""


@dataclass(frozen=True)
class ArtifactDownloadTarget:
    path: Path
    filename: str
    media_type: str
    content_disposition_type: str = "attachment"


@dataclass(frozen=True)
class ArtifactCleanupPolicy:
    name: str
    root: Path
    suffixes: frozenset[str]
    recursive: bool = False


def compile_pdf_root() -> Path:
    return Path(settings.COMPILE_WORK_DIR) / "pdfs"


def export_root() -> Path:
    return Path(settings.UPLOAD_DIR) / "exports"


def lesson_artifact_root() -> Path:
    if settings.LESSON_ARTIFACT_ROOT:
        return Path(settings.LESSON_ARTIFACT_ROOT)
    return Path(settings.UPLOAD_DIR) / "lessons"


def trusted_artifact_roots() -> tuple[Path, ...]:
    return (compile_pdf_root(), export_root(), lesson_artifact_root())


def artifact_cleanup_policies() -> tuple[ArtifactCleanupPolicy, ...]:
    return (
        ArtifactCleanupPolicy("compile_pdf", compile_pdf_root(), frozenset({".pdf"})),
        ArtifactCleanupPolicy("export", export_root(), frozenset(EXPORT_MEDIA_TYPES)),
        ArtifactCleanupPolicy(
            "lesson",
            lesson_artifact_root(),
            frozenset({".webm", ".wav", ".mp3", ".m4a", ".ogg", ".mp4", ".tex"}),
            recursive=True,
        ),
    )


def _artifact_config(kind: ArtifactKind) -> tuple[Path, dict[str, str], str]:
    if kind == "compile_pdf":
        return compile_pdf_root(), COMPILE_MEDIA_TYPES, "inline"
    if kind == "export":
        return export_root(), EXPORT_MEDIA_TYPES, "attachment"
    raise UnsupportedArtifactTypeError(f"Unsupported artifact kind: {kind}")


def _validate_download_filename(filename: str) -> str:
    if not filename or filename.strip() != filename:
        raise InvalidArtifactFilenameError("Invalid artifact filename")
    if any(ord(char) < 32 for char in filename):
        raise InvalidArtifactFilenameError("Invalid artifact filename")
    if "/" in filename or "\\" in filename:
        raise InvalidArtifactFilenameError("Invalid artifact filename")
    if filename in {".", ".."} or ".." in Path(filename).parts:
        raise InvalidArtifactFilenameError("Invalid artifact filename")
    if Path(filename).name != filename:
        raise InvalidArtifactFilenameError("Invalid artifact filename")
    return filename


def _resolve_inside_root(root: Path, filename: str) -> Path:
    resolved_root = root.resolve()
    resolved_path = (resolved_root / filename).resolve()
    if resolved_path != resolved_root and resolved_root in resolved_path.parents:
        return resolved_path
    raise InvalidArtifactFilenameError("Artifact path escapes configured artifact directory")


def resolve_artifact_download(kind: ArtifactKind, filename: str) -> ArtifactDownloadTarget:
    """Resolve a safe downloadable artifact path for compile/export endpoints."""
    safe_filename = _validate_download_filename(filename)
    root, media_types, disposition = _artifact_config(kind)
    suffix = Path(safe_filename).suffix.lower()
    media_type = media_types.get(suffix)
    if media_type is None:
        raise UnsupportedArtifactTypeError("Unsupported artifact file type")
    return ArtifactDownloadTarget(
        path=_resolve_inside_root(root, safe_filename),
        filename=safe_filename,
        media_type=media_type,
        content_disposition_type=disposition,
    )


def ensure_trusted_artifact_root(directory: Path, trusted_roots: tuple[Path, ...] | None = None) -> Path:
    """Resolve and validate an artifact cleanup root against trusted artifact roots."""
    resolved_directory = directory.resolve()
    roots = trusted_roots or trusted_artifact_roots()
    resolved_roots = tuple(root.resolve() for root in roots)
    if any(resolved_directory == root for root in resolved_roots):
        return resolved_directory
    raise InvalidArtifactFilenameError("Cleanup directory is not a trusted artifact root")
