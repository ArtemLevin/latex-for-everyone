import hashlib
import json
import re
import shutil
import subprocess
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


class AudioDurationTooLongError(AudioStorageError):
    """Raised when a probed audio duration exceeds configured limits."""


@dataclass(frozen=True)
class ValidatedAudioUpload:
    original_filename: str
    suffix: str
    content_type: str
    size_bytes: int
    sha256_checksum: str


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
        sha256_checksum=hashlib.sha256(payload).hexdigest(),
    )


def resolve_inside_root(root: Path, *parts: str) -> Path:
    resolved_root = root.resolve()
    target = resolved_root.joinpath(*parts).resolve()
    if target == resolved_root or resolved_root in target.parents:
        return target
    raise InvalidAudioFilenameError("Audio storage path escapes lesson artifact root")


def probe_audio_duration_seconds(audio_path: Path) -> float | None:
    """Best-effort ffprobe duration extraction for already trusted local audio."""

    if not settings.LESSON_AUDIO_DURATION_PROBE_ENABLED:
        return None
    if shutil.which("ffprobe") is None:
        return None

    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(audio_path),
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if result.returncode != 0:
        return None

    try:
        raw_duration = json.loads(result.stdout or "{}").get("format", {}).get("duration")
        duration = float(raw_duration)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if duration <= 0:
        return None
    return duration


def validate_audio_duration(duration_seconds: float | None) -> None:
    max_duration = settings.MAX_LESSON_AUDIO_DURATION_SECONDS
    if duration_seconds is None or max_duration <= 0:
        return
    if duration_seconds > max_duration:
        raise AudioDurationTooLongError("Audio duration exceeds configured limit")


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
        duration_seconds = probe_audio_duration_seconds(target_path)
        try:
            validate_audio_duration(duration_seconds)
        except AudioDurationTooLongError:
            target_path.unlink(missing_ok=True)
            raise

        recording = LessonAudioRecording(
            id=recording_id,
            lesson_id=lesson.id,
            filename=validated.original_filename,
            content_type=validated.content_type,
            size_bytes=validated.size_bytes,
            duration_seconds=duration_seconds,
            sha256_checksum=validated.sha256_checksum,
            storage_path=str(Path(*relative_parts).as_posix()),
            status="uploaded",
        )
        lesson.status = "recording_uploaded"
        lesson.updated_at = utc_now()
        db.add(recording)
        db.commit()
        db.refresh(recording)
        return recording
