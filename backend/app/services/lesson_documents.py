import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Lesson, LessonGeneratedDocument, LessonTranscript, Pupil
from app.services.audio_storage import lesson_artifact_root, resolve_inside_root, safe_path_part
from app.services.latex_document_builder import build_latex_document
from app.services.transcription import effective_transcript_text
from app.time_utils import utc_now


DOCUMENT_TYPES = ("check_list", "pupil_mistakes")
PROMPT_DIR = Path(__file__).resolve().parents[1] / "prompts" / "lesson"
HARD_CODED_PROMPT_TOKENS = ("Николь", "[ФИО ученика: Николь, ЕГЭ]")


class LessonDocumentError(Exception):
    """Base error for lesson document generation."""


class LessonTranscriptNotFoundError(LessonDocumentError):
    """Raised when no completed transcript can be used for document generation."""


class LessonDocumentNotFoundError(LessonDocumentError):
    """Raised when a generated document does not exist in the current lesson scope."""


class LessonPromptError(LessonDocumentError):
    """Raised when a prompt template is missing or unsafe."""


class LessonDocumentProviderError(LessonDocumentError):
    """Raised when a document provider cannot return structured content."""


@dataclass(frozen=True)
class LessonDocumentContext:
    lesson: Lesson
    pupil: Pupil
    transcript: LessonTranscript


@dataclass(frozen=True)
class LessonDocumentDraft:
    document_type: str
    title: str
    sections: dict[str, list[str]]


class LessonDocumentProvider(Protocol):
    provider_name: str

    async def generate(self, *, document_type: str, prompt: str, context: LessonDocumentContext) -> LessonDocumentDraft:
        """Generate a structured draft for a lesson document."""


class FakeLessonDocumentProvider:
    provider_name = "fake"

    async def generate(self, *, document_type: str, prompt: str, context: LessonDocumentContext) -> LessonDocumentDraft:
        topic = context.lesson.topic
        transcript_preview = " ".join(effective_transcript_text(context.transcript).split())[:240]
        if document_type == "check_list":
            return LessonDocumentDraft(
                document_type=document_type,
                title=f"Чек-лист по теме: {topic}",
                sections={
                    "Цели занятия": [f"Повторить ключевые идеи темы: {topic}"],
                    "Что удалось": ["Зафиксирован рабочий транскрипт занятия", transcript_preview or "Транскрипт пуст"],
                    "Домашняя работа": ["Повторить определения", "Решить 3–5 похожих задач"],
                    "Следующие шаги": ["Вернуться к сложным местам на следующем занятии"],
                },
            )
        if document_type == "pupil_mistakes":
            return LessonDocumentDraft(
                document_type=document_type,
                title=f"Разбор ошибок: {topic}",
                sections={
                    "Наблюдения": [transcript_preview or "Недостаточно данных для точного вывода"],
                    "Вероятные зоны риска": ["Проверить вычисления и оформление решения", "Отдельно контролировать область допустимых значений"],
                    "Тренировка": ["Составить краткий конспект метода", "Решить дополнительную задачу с самопроверкой"],
                },
            )
        raise LessonDocumentProviderError(f"Unsupported lesson document type: {document_type}")


class DisabledLessonDocumentProvider:
    provider_name = "disabled"

    async def generate(self, *, document_type: str, prompt: str, context: LessonDocumentContext) -> LessonDocumentDraft:
        raise LessonDocumentProviderError("Lesson document provider is disabled")


class LessonPromptService:
    def __init__(self, prompt_dir: Path = PROMPT_DIR):
        self.prompt_dir = prompt_dir

    def load(self, document_type: str) -> str:
        if document_type not in DOCUMENT_TYPES:
            raise LessonPromptError(f"Unsupported lesson document type: {document_type}")
        prompt_path = self.prompt_dir / f"{document_type}.txt"
        try:
            template = prompt_path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise LessonPromptError(f"Lesson prompt template not found: {document_type}") from exc
        for token in HARD_CODED_PROMPT_TOKENS:
            if token in template:
                raise LessonPromptError("Lesson prompt template contains hardcoded pupil data")
        return template

    def render(self, document_type: str, context: LessonDocumentContext) -> str:
        template = self.load(document_type)
        replacements = {
            "{{ pupil_display_name }}": context.pupil.display_name,
            "{{ lesson_topic }}": context.lesson.topic,
            "{{ lesson_date }}": context.lesson.lesson_date.isoformat(),
            "{{ transcript_text }}": effective_transcript_text(context.transcript),
        }
        rendered = template
        for placeholder, value in replacements.items():
            rendered = rendered.replace(placeholder, value)
        return rendered


def build_lesson_document_provider() -> LessonDocumentProvider:
    provider = settings.LESSON_DOCUMENT_PROVIDER.strip().lower()
    if provider == "fake":
        return FakeLessonDocumentProvider()
    return DisabledLessonDocumentProvider()


def latex_escape(value: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(char, char) for char in value)


def slugify_filename_part(value: str) -> str:
    slug = safe_path_part(value.lower())
    return slug[:80] or "lesson"


def build_lesson_latex_document(draft: LessonDocumentDraft, context: LessonDocumentContext) -> str:
    body_parts = [
        rf"\section*{{{latex_escape(draft.title)}}}",
        rf"\textbf{{Ученик:}} {latex_escape(context.pupil.display_name)}\\",
        rf"\textbf{{Тема:}} {latex_escape(context.lesson.topic)}",
    ]
    for heading, items in draft.sections.items():
        body_parts.append(rf"\subsection*{{{latex_escape(heading)}}}")
        body_parts.append(r"\begin{itemize}")
        for item in items:
            body_parts.append(rf"\item {latex_escape(item)}")
        body_parts.append(r"\end{itemize}")
    return build_latex_document("\n\n".join(body_parts))


def configured_document_types() -> list[str]:
    requested = [item.strip() for item in settings.LESSON_DOCUMENT_ALLOWED_TYPES.split(",") if item.strip()]
    selected = [item for item in requested if item in DOCUMENT_TYPES]
    return selected or list(DOCUMENT_TYPES)


class LessonDocumentGenerationService:
    """Generate and persist safe lesson document artifacts from transcripts."""

    def __init__(self, prompt_service: LessonPromptService | None = None, provider: LessonDocumentProvider | None = None):
        self.prompt_service = prompt_service or LessonPromptService()
        self.provider = provider or build_lesson_document_provider()

    def get_transcript(self, db: Session, *, lesson: Lesson, transcript_id: str | None = None) -> LessonTranscript:
        query = db.query(LessonTranscript).filter(
            LessonTranscript.lesson_id == lesson.id,
            LessonTranscript.status == "completed",
        )
        if transcript_id:
            query = query.filter(LessonTranscript.id == transcript_id)
        transcript = query.order_by(LessonTranscript.created_at.desc()).first()
        if not transcript:
            raise LessonTranscriptNotFoundError("Completed lesson transcript not found")
        return transcript

    def list_documents(self, db: Session, *, lesson: Lesson) -> list[LessonGeneratedDocument]:
        return (
            db.query(LessonGeneratedDocument)
            .filter(LessonGeneratedDocument.lesson_id == lesson.id)
            .order_by(LessonGeneratedDocument.created_at.desc())
            .all()
        )

    def get_document(self, db: Session, *, lesson: Lesson, document_id: str) -> LessonGeneratedDocument:
        document = (
            db.query(LessonGeneratedDocument)
            .filter(LessonGeneratedDocument.id == document_id, LessonGeneratedDocument.lesson_id == lesson.id)
            .first()
        )
        if not document:
            raise LessonDocumentNotFoundError("Lesson document not found")
        return document

    async def generate_documents(
        self,
        db: Session,
        *,
        lesson: Lesson,
        document_types: list[str] | None = None,
        transcript_id: str | None = None,
    ) -> list[LessonGeneratedDocument]:
        transcript = self.get_transcript(db, lesson=lesson, transcript_id=transcript_id)
        if not lesson.pupil:
            raise LessonDocumentProviderError("Lesson pupil is unavailable")
        selected_types = document_types or configured_document_types()
        context = LessonDocumentContext(lesson=lesson, pupil=lesson.pupil, transcript=transcript)
        documents: list[LessonGeneratedDocument] = []
        for document_type in selected_types:
            prompt = self.prompt_service.render(document_type, context)
            draft = await self.provider.generate(document_type=document_type, prompt=prompt, context=context)
            documents.append(self._persist_document(db, context=context, draft=draft))
        lesson.status = "completed"
        lesson.updated_at = utc_now()
        db.commit()
        for document in documents:
            db.refresh(document)
        return documents

    def _persist_document(self, db: Session, *, context: LessonDocumentContext, draft: LessonDocumentDraft) -> LessonGeneratedDocument:
        document_id = str(uuid.uuid4())
        topic_slug = slugify_filename_part(context.lesson.topic)
        filename = f"{draft.document_type}_{topic_slug}_{document_id}.tex"
        lesson_date = context.lesson.lesson_date.date().isoformat()
        relative_parts = (
            f"teacher_{safe_path_part(context.lesson.teacher_id)}",
            f"pupil_{safe_path_part(context.lesson.pupil_id)}",
            lesson_date,
            f"lesson_{safe_path_part(context.lesson.id)}",
            "documents",
            filename,
        )
        target_path = resolve_inside_root(lesson_artifact_root(), *relative_parts)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(build_lesson_latex_document(draft, context), encoding="utf-8")
        document = LessonGeneratedDocument(
            id=document_id,
            lesson_id=context.lesson.id,
            transcript_id=context.transcript.id,
            document_type=draft.document_type,
            title=draft.title,
            filename=filename,
            content_type="application/x-tex",
            storage_path=str(Path(*relative_parts).as_posix()),
            status="completed",
            error_message=None,
        )
        db.add(document)
        return document

    def resolve_document_path(self, document: LessonGeneratedDocument) -> Path:
        return resolve_inside_root(lesson_artifact_root(), document.storage_path)
