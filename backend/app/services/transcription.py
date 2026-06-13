import importlib
import importlib.util
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType
from typing import Protocol

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Lesson, LessonAudioRecording, LessonTranscript
from app.services.audio_storage import lesson_artifact_root, resolve_inside_root
from app.time_utils import utc_now


class TranscriptionError(Exception):
    """Base error for lesson transcription workflows."""


class RecordingNotFoundError(TranscriptionError):
    """Raised when a lesson has no matching audio recording."""


class TranscriptionProviderError(TranscriptionError):
    """Raised when the configured transcription provider cannot transcribe audio."""


@dataclass(frozen=True)
class TranscriptSegment:
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class TranscriptResult:
    text: str
    language: str
    provider: str
    duration_seconds: float | None = None
    confidence: float | None = None
    segments: list[TranscriptSegment] = field(default_factory=list)


class TranscriptionProvider(Protocol):
    provider_name: str

    def transcribe(self, audio_path: Path, *, language: str) -> TranscriptResult:
        """Return a transcript for a trusted local audio path."""


class DisabledTranscriptionProvider:
    provider_name = "disabled"

    def transcribe(self, audio_path: Path, *, language: str) -> TranscriptResult:
        raise TranscriptionProviderError("Transcription provider is disabled")


class FakeTranscriptionProvider:
    provider_name = "fake"

    def __init__(self, text: str = "Тестовая транскрибация занятия", *, fail: bool = False):
        self.text = text
        self.fail = fail

    def transcribe(self, audio_path: Path, *, language: str) -> TranscriptResult:
        if self.fail:
            raise TranscriptionProviderError("Fake transcription provider failed")
        return TranscriptResult(
            text=self.text,
            language=language,
            provider=self.provider_name,
            segments=[TranscriptSegment(start=0.0, end=1.0, text=self.text)],
        )


def load_legacy_transcibe_module() -> ModuleType:
    script_path = Path(__file__).resolve().parents[3] / "transcibe.py"
    spec = importlib.util.spec_from_file_location("latexed_legacy_transcibe", script_path)
    if spec is None or spec.loader is None:
        raise TranscriptionProviderError("Legacy transcription script is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class LegacyWhisperTranscriptionProvider:
    """Adapter around the legacy root-level `transcibe.py` script.

    The public backend service uses the correctly spelled transcription naming;
    the legacy typo is contained here and is never imported by routers.
    """

    provider_name = "legacy_whisper"

    def __init__(self, *, model_name: str, beam_size: int):
        self.model_name = model_name
        self.beam_size = beam_size

    def transcribe(self, audio_path: Path, *, language: str) -> TranscriptResult:
        legacy_script = load_legacy_transcibe_module()
        legacy_script.ensure_ffmpeg_tools()
        duration_seconds = legacy_script.get_audio_duration_seconds(audio_path)
        model = legacy_script.whisper.load_model(self.model_name)

        with TemporaryDirectory(prefix="latexed_transcribe_") as tmp_dir:
            prepared_wav = Path(tmp_dir) / f"{audio_path.stem}_prepared.wav"
            legacy_script.prepare_audio_for_whisper(audio_path, prepared_wav)
            text, lines = legacy_script.transcribe_audio_file(
                model=model,
                prepared_audio_file=prepared_wav,
                language=language,
                beam_size=self.beam_size,
            )

        segments = [
            TranscriptSegment(start=float(line.start), end=float(line.end), text=str(line.text))
            for line in lines
        ]
        return TranscriptResult(
            text=text,
            language=language,
            provider=self.provider_name,
            duration_seconds=duration_seconds,
            segments=segments,
        )


class FasterWhisperTranscriptionProvider:
    """Optional production-oriented provider backed by `faster-whisper`.

    The dependency is intentionally loaded only when this provider is used so the
    default development/CI path can keep `TRANSCRIPTION_PROVIDER=disabled` or
    `fake` without installing model/runtime packages.
    """

    provider_name = "faster_whisper"

    def __init__(self, *, model_name: str, device: str, compute_type: str, beam_size: int, word_timestamps: bool):
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self.beam_size = beam_size
        self.word_timestamps = word_timestamps

    def transcribe(self, audio_path: Path, *, language: str) -> TranscriptResult:
        faster_whisper = importlib.import_module("faster_whisper")
        model = faster_whisper.WhisperModel(
            self.model_name,
            device=self.device,
            compute_type=self.compute_type,
        )
        raw_segments, info = model.transcribe(
            str(audio_path),
            language=language,
            beam_size=self.beam_size,
            word_timestamps=self.word_timestamps,
        )
        segments = [
            TranscriptSegment(
                start=float(getattr(segment, "start", 0.0)),
                end=float(getattr(segment, "end", 0.0)),
                text=str(getattr(segment, "text", "")).strip(),
            )
            for segment in raw_segments
        ]
        text = "\n".join(segment.text for segment in segments if segment.text).strip()
        if not text:
            raise TranscriptionProviderError("Transcription provider returned empty text")
        detected_language = str(getattr(info, "language", None) or language)
        duration = getattr(info, "duration", None)
        return TranscriptResult(
            text=text,
            language=detected_language,
            provider=self.provider_name,
            duration_seconds=float(duration) if duration is not None else None,
            segments=segments,
        )


def build_disabled_transcription_provider() -> TranscriptionProvider:
    return DisabledTranscriptionProvider()


def build_fake_transcription_provider() -> TranscriptionProvider:
    return FakeTranscriptionProvider()


def build_legacy_whisper_transcription_provider() -> TranscriptionProvider:
    return LegacyWhisperTranscriptionProvider(
        model_name=settings.TRANSCRIPTION_MODEL,
        beam_size=settings.TRANSCRIPTION_BEAM_SIZE,
    )


def build_faster_whisper_transcription_provider() -> TranscriptionProvider:
    return FasterWhisperTranscriptionProvider(
        model_name=settings.TRANSCRIPTION_MODEL,
        device=settings.TRANSCRIPTION_DEVICE,
        compute_type=settings.TRANSCRIPTION_COMPUTE_TYPE,
        beam_size=settings.TRANSCRIPTION_BEAM_SIZE,
        word_timestamps=settings.TRANSCRIPTION_WORD_TIMESTAMPS,
    )


TRANSCRIPTION_PROVIDER_REGISTRY = {
    "disabled": build_disabled_transcription_provider,
    "fake": build_fake_transcription_provider,
    "legacy_whisper": build_legacy_whisper_transcription_provider,
    "whisper": build_legacy_whisper_transcription_provider,
    "faster_whisper": build_faster_whisper_transcription_provider,
}


def available_transcription_providers() -> tuple[str, ...]:
    return tuple(sorted(TRANSCRIPTION_PROVIDER_REGISTRY))


def build_transcription_provider() -> TranscriptionProvider:
    provider = settings.TRANSCRIPTION_PROVIDER.strip().lower()
    factory = TRANSCRIPTION_PROVIDER_REGISTRY.get(provider, build_disabled_transcription_provider)
    return factory()


def sanitize_provider_error(exc: Exception) -> str:
    message = str(exc).strip() or "Transcription provider failed"
    single_line = " ".join(message.split())
    return single_line[:500]


class TranscriptionService:
    """Synchronous MVP transcription workflow for lesson recordings."""

    def __init__(self, provider: TranscriptionProvider | None = None):
        self.provider = provider or build_transcription_provider()

    def get_recording(
        self,
        db: Session,
        *,
        lesson: Lesson,
        recording_id: str | None = None,
    ) -> LessonAudioRecording:
        query = db.query(LessonAudioRecording).filter(LessonAudioRecording.lesson_id == lesson.id)
        if recording_id:
            query = query.filter(LessonAudioRecording.id == recording_id)
        recording = query.order_by(LessonAudioRecording.created_at.desc()).first()
        if not recording:
            raise RecordingNotFoundError("Recording not found")
        return recording

    def transcribe_lesson(
        self,
        db: Session,
        *,
        lesson: Lesson,
        recording_id: str | None = None,
        language: str | None = None,
    ) -> LessonTranscript:
        recording = self.get_recording(db, lesson=lesson, recording_id=recording_id)
        transcript_language = language or settings.TRANSCRIPTION_LANGUAGE
        transcript_id = str(uuid.uuid4())
        audio_path = resolve_inside_root(lesson_artifact_root(), recording.storage_path)

        try:
            result = self.provider.transcribe(audio_path, language=transcript_language)
        except Exception as exc:
            transcript = LessonTranscript(
                id=transcript_id,
                lesson_id=lesson.id,
                recording_id=recording.id,
                provider=getattr(self.provider, "provider_name", settings.TRANSCRIPTION_PROVIDER),
                language=transcript_language,
                text=None,
                status="failed",
                error_message=sanitize_provider_error(exc),
            )
            db.add(transcript)
            db.commit()
            db.refresh(transcript)
            return transcript

        transcript = LessonTranscript(
            id=transcript_id,
            lesson_id=lesson.id,
            recording_id=recording.id,
            provider=result.provider,
            language=result.language,
            text=result.text,
            status="completed",
        )
        recording.status = "transcribed"
        if result.duration_seconds is not None:
            recording.duration_seconds = result.duration_seconds
        recording.updated_at = utc_now()
        lesson.status = "transcript_ready"
        lesson.updated_at = utc_now()
        db.add(transcript)
        db.commit()
        db.refresh(transcript)
        return transcript
