import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Lesson, LessonAudioRecording
from app.time_utils import utc_now


class AudioStorageError(Exception):
    """Base error for lesson audio storage."""


class InvalidAudioFilenameError(AudioStorageError):
    """Raised when an uploaded audio filename is unsafe."""


class UnsupportedAudioTypeError(AudioStorageError):
    """Raised when an uploaded audio file type is unsupported."""


class AudioPayloadTooLargeError(AudioStorageError):
    """Raised when an uploaded audio payload exceeds configured limits."""


@dataclass(frozen=True)
class ValidatedAudioUpload:
    original_filename: str
    suffix: str
    content_type: str
    size_bytes: int


def lesson_artifact_root() -> Path:
    configured_root = settings.LESSON_ARTIFACT_ROOT
    if configured_root:
        return Path(configured_root)
    return Path(settings.UPLOAD_DIR) / "lessons"


def parse_csv_setting(value: str) -> set[str]:
    return {item.strip().lower() for item in value.split(",") if item.strip()}


def safe_path_part(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip(".-")
    return slug or "unknown"


def validate_audio_filename(filename: str) -> str:
    if not filename or filename.strip() != filename:
        raise InvalidAudioFilenameError("Invalid audio filename")
    if any(ord(char) < 32 for char in filename):
        raise InvalidAudioFilenameError("Invalid audio filename")
    if "/" in filename or "\\" in filename:
        raise InvalidAudioFilenameError("Invalid audio filename")
    if filename in {".", ".."} or ".." in Path(filename).parts:
        raise InvalidAudioFilenameError("Invalid audio filename")
    if Path(filename).name != filename:
        raise InvalidAudioFilenameError("Invalid audio filename")
    return filename


def validate_audio_upload(filename: str, content_type: str | None, payload: bytes) -> ValidatedAudioUpload:
    safe_filename = validate_audio_filename(filename)
    suffix = Path(safe_filename).suffix.lower()
    allowed_extensions = parse_csv_setting(settings.LESSON_AUDIO_ALLOWED_EXTENSIONS)
    if suffix not in allowed_extensions:
        raise UnsupportedAudioTypeError("Unsupported audio file extension")

    normalized_content_type = (content_type or "").split(";", 1)[0].strip().lower()
    allowed_content_types = parse_csv_setting(settings.LESSON_AUDIO_ALLOWED_CONTENT_TYPES)
    if normalized_content_type not in allowed_content_types:
        raise UnsupportedAudioTypeError("Unsupported audio content type")

    size_bytes = len(payload)
    if size_bytes > settings.MAX_LESSON_AUDIO_SIZE:
        raise AudioPayloadTooLargeError("Audio payload exceeds configured size limit")

    return ValidatedAudioUpload(
        original_filename=safe_filename,
        suffix=suffix,
        content_type=normalized_content_type,
        size_bytes=size_bytes,
    )


def resolve_inside_root(root: Path, *parts: str) -> Path:
    resolved_root = root.resolve()
    target = resolved_root.joinpath(*parts).resolve()
    if target == resolved_root or resolved_root in target.parents:
        return target
    raise InvalidAudioFilenameError("Audio storage path escapes lesson artifact root")


class AudioStorageService:
    """Safe storage workflow for lesson audio uploads."""

    def create_recording(
        self,
        db: Session,
        *,
        lesson: Lesson,
        teacher_id: str,
        filename: str,
        content_type: str | None,
        payload: bytes,
    ) -> LessonAudioRecording:
        validated = validate_audio_upload(filename, content_type, payload)
        recording_id = str(uuid.uuid4())
        root = lesson_artifact_root()
        lesson_date = lesson.lesson_date.date().isoformat()
        relative_parts = (
            f"teacher_{safe_path_part(teacher_id)}",
            f"pupil_{safe_path_part(lesson.pupil_id)}",
            lesson_date,
            f"lesson_{safe_path_part(lesson.id)}",
            "audio",
            f"recording_{recording_id}{validated.suffix}",
        )
        target_path = resolve_inside_root(root, *relative_parts)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(payload)

        recording = LessonAudioRecording(
            id=recording_id,
            lesson_id=lesson.id,
            filename=validated.original_filename,
            content_type=validated.content_type,
            size_bytes=validated.size_bytes,
            storage_path=str(Path(*relative_parts).as_posix()),
            status="uploaded",
        )
        lesson.status = "recording_uploaded"
        lesson.updated_at = utc_now()
        db.add(recording)
        db.commit()
        db.refresh(recording)
        return recording
