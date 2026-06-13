import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import Lesson, LessonGeneratedDocument, LessonProcessingJob, LessonTranscript
from app.schemas import LessonProcessingJobCreate
from app.services.lesson_documents import DOCUMENT_TYPES, LessonDocumentGenerationService, LessonTranscriptNotFoundError
from app.services.transcription import RecordingNotFoundError, TranscriptionService
from app.time_utils import utc_now


TERMINAL_JOB_STATUSES = {"completed", "failed", "canceled"}
ACTIVE_JOB_STATUSES = {"queued", "running"}


class LessonJobError(Exception):
    """Base error for lesson processing jobs."""


class LessonJobNotFoundError(LessonJobError):
    """Raised when a job is not visible in the current teacher/lesson scope."""


class LessonJobConflictError(LessonJobError):
    """Raised when a new job would conflict with an active job."""


@dataclass(frozen=True)
class LessonJobResult:
    job: LessonProcessingJob
    created: bool = True


class LessonProcessingJobService:
    """Worker-friendly orchestration for lesson processing stages.

    This service persists status transitions and can be called by HTTP handlers today
    or by an out-of-process worker later without changing the job state contract.
    """

    def __init__(
        self,
        *,
        transcription_service: TranscriptionService | None = None,
        document_service: LessonDocumentGenerationService | None = None,
    ):
        self.transcription_service = transcription_service or TranscriptionService()
        self.document_service = document_service or LessonDocumentGenerationService()

    def list_jobs(self, db: Session, *, lesson: Lesson) -> list[LessonProcessingJob]:
        return (
            db.query(LessonProcessingJob)
            .filter(LessonProcessingJob.lesson_id == lesson.id, LessonProcessingJob.teacher_id == lesson.teacher_id)
            .order_by(LessonProcessingJob.created_at.desc())
            .all()
        )

    def get_job(self, db: Session, *, lesson: Lesson, job_id: str) -> LessonProcessingJob:
        job = (
            db.query(LessonProcessingJob)
            .filter(
                LessonProcessingJob.id == job_id,
                LessonProcessingJob.lesson_id == lesson.id,
                LessonProcessingJob.teacher_id == lesson.teacher_id,
            )
            .first()
        )
        if not job:
            raise LessonJobNotFoundError("Lesson processing job not found")
        return job

    async def create_and_run_job(self, db: Session, *, lesson: Lesson, request: LessonProcessingJobCreate) -> LessonProcessingJob:
        self._ensure_no_active_job(db, lesson=lesson, job_type=request.job_type)
        job = LessonProcessingJob(
            id=str(uuid.uuid4()),
            lesson_id=lesson.id,
            teacher_id=lesson.teacher_id,
            job_type=request.job_type,
            status="queued",
            stage="queued",
            recording_id=request.recording_id,
            transcript_id=request.transcript_id,
            document_ids=[],
            attempts=0,
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        await self.run_job(db, lesson=lesson, job=job, request=request)
        db.refresh(job)
        return job

    async def run_job(self, db: Session, *, lesson: Lesson, job: LessonProcessingJob, request: LessonProcessingJobCreate) -> LessonProcessingJob:
        self._mark_running(db, job, stage="starting")
        try:
            if request.job_type == "transcribe":
                await self._run_transcription_stage(db, lesson=lesson, job=job, recording_id=request.recording_id)
            elif request.job_type == "generate_documents":
                await self._run_document_stage(
                    db,
                    lesson=lesson,
                    job=job,
                    transcript_id=request.transcript_id,
                    document_types=request.document_types,
                )
            else:
                transcript_id = request.transcript_id
                if not transcript_id:
                    transcript = self._latest_completed_transcript(db, lesson=lesson)
                    if transcript:
                        transcript_id = transcript.id
                    else:
                        transcript = await self._run_transcription_stage(
                            db,
                            lesson=lesson,
                            job=job,
                            recording_id=request.recording_id,
                        )
                        transcript_id = transcript.id
                await self._run_document_stage(
                    db,
                    lesson=lesson,
                    job=job,
                    transcript_id=transcript_id,
                    document_types=request.document_types,
                )
            self._mark_completed(db, job)
        except Exception as exc:
            self._mark_failed(db, job, str(exc) or "Lesson processing job failed")
        return job

    def _ensure_no_active_job(self, db: Session, *, lesson: Lesson, job_type: str) -> None:
        active_job = (
            db.query(LessonProcessingJob)
            .filter(
                LessonProcessingJob.lesson_id == lesson.id,
                LessonProcessingJob.teacher_id == lesson.teacher_id,
                LessonProcessingJob.job_type == job_type,
                LessonProcessingJob.status.in_(ACTIVE_JOB_STATUSES),
            )
            .first()
        )
        if active_job:
            raise LessonJobConflictError("A lesson processing job is already running")

    def _mark_running(self, db: Session, job: LessonProcessingJob, *, stage: str) -> None:
        now = utc_now()
        job.status = "running"
        job.stage = stage
        job.started_at = job.started_at or now
        job.updated_at = now
        job.attempts += 1
        db.commit()
        db.refresh(job)

    def _mark_stage(self, db: Session, job: LessonProcessingJob, *, stage: str) -> None:
        job.stage = stage
        job.updated_at = utc_now()
        db.commit()
        db.refresh(job)

    def _mark_completed(self, db: Session, job: LessonProcessingJob) -> None:
        now = utc_now()
        job.status = "completed"
        job.stage = "completed"
        job.finished_at = now
        job.updated_at = now
        job.error_message = None
        db.commit()
        db.refresh(job)

    def _mark_failed(self, db: Session, job: LessonProcessingJob, message: str) -> None:
        now = utc_now()
        job.status = "failed"
        job.stage = "failed"
        job.finished_at = now
        job.updated_at = now
        job.error_message = " ".join(message.split())[:500]
        db.commit()
        db.refresh(job)

    async def _run_transcription_stage(
        self,
        db: Session,
        *,
        lesson: Lesson,
        job: LessonProcessingJob,
        recording_id: str | None,
    ) -> LessonTranscript:
        self._mark_stage(db, job, stage="transcribing")
        transcript = self.transcription_service.transcribe_lesson(
            db,
            lesson=lesson,
            recording_id=recording_id,
            language=None,
        )
        job.transcript_id = transcript.id
        job.recording_id = transcript.recording_id
        job.updated_at = utc_now()
        db.commit()
        db.refresh(job)
        if transcript.status != "completed":
            raise RecordingNotFoundError(transcript.error_message or "Transcription failed")
        return transcript

    async def _run_document_stage(
        self,
        db: Session,
        *,
        lesson: Lesson,
        job: LessonProcessingJob,
        transcript_id: str | None,
        document_types: list[str],
    ) -> list[LessonGeneratedDocument]:
        self._mark_stage(db, job, stage="generating_documents")
        if transcript_id and not self._transcript_exists(db, lesson=lesson, transcript_id=transcript_id):
            raise LessonTranscriptNotFoundError("Completed lesson transcript not found")
        requested_types = document_types or list(DOCUMENT_TYPES)
        existing_documents = self.document_service.list_documents(db, lesson=lesson)
        documents_by_type = {document.document_type: document for document in existing_documents if document.status == "completed"}
        missing_types = [document_type for document_type in requested_types if document_type not in documents_by_type]

        generated_documents: list[LessonGeneratedDocument] = []
        if missing_types:
            generated_documents = await self.document_service.generate_documents(
                db,
                lesson=lesson,
                document_types=missing_types,
                transcript_id=transcript_id,
            )
        all_documents = [documents_by_type[document_type] for document_type in requested_types if document_type in documents_by_type]
        all_documents.extend(generated_documents)
        job.document_ids = [document.id for document in all_documents]
        if transcript_id:
            job.transcript_id = transcript_id
        elif generated_documents:
            job.transcript_id = generated_documents[0].transcript_id
        job.updated_at = utc_now()
        db.commit()
        db.refresh(job)
        return all_documents

    def _latest_completed_transcript(self, db: Session, *, lesson: Lesson) -> LessonTranscript | None:
        return (
            db.query(LessonTranscript)
            .filter(LessonTranscript.lesson_id == lesson.id, LessonTranscript.status == "completed")
            .order_by(LessonTranscript.created_at.desc())
            .first()
        )

    def _transcript_exists(self, db: Session, *, lesson: Lesson, transcript_id: str) -> bool:
        return (
            db.query(LessonTranscript)
            .filter(
                LessonTranscript.id == transcript_id,
                LessonTranscript.lesson_id == lesson.id,
                LessonTranscript.status == "completed",
            )
            .first()
            is not None
        )
