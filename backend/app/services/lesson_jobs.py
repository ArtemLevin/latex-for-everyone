import logging
import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Lesson, LessonGeneratedDocument, LessonProcessingJob, LessonTranscript
from app.schemas import LessonProcessingJobCreate
from app.services.lesson_documents import DOCUMENT_TYPES, LessonDocumentGenerationService, LessonTranscriptNotFoundError
from app.services.transcription import RecordingNotFoundError, TranscriptionService
from app.time_utils import utc_now


logger = logging.getLogger(__name__)


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

    HTTP handlers can create queued jobs and either run them inline for the current
    development/test baseline or hand the job id to an in-process/background or
    external worker without changing the persisted state contract.
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

    def create_job(self, db: Session, *, lesson: Lesson, request: LessonProcessingJobCreate) -> LessonProcessingJob:
        logger.info("lesson job create requested lesson_id=%s teacher_id=%s job_type=%s recording_id=%s transcript_id=%s document_types=%s", lesson.id, lesson.teacher_id, request.job_type, request.recording_id, request.transcript_id, list(request.document_types))
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
            document_types=list(request.document_types),
            document_ids=[],
            attempts=0,
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        logger.info("lesson job queued job_id=%s lesson_id=%s job_type=%s stage=%s", job.id, lesson.id, job.job_type, job.stage)
        return job

    async def create_and_run_job(self, db: Session, *, lesson: Lesson, request: LessonProcessingJobCreate) -> LessonProcessingJob:
        logger.info("lesson job create_and_run requested lesson_id=%s job_type=%s", lesson.id, request.job_type)
        job = self.create_job(db, lesson=lesson, request=request)
        await self.run_job(db, lesson=lesson, job=job, request=request)
        db.refresh(job)
        return job

    async def run_existing_job(self, db: Session, *, job_id: str) -> LessonProcessingJob:
        logger.info("lesson job run_existing requested job_id=%s", job_id)
        job = db.query(LessonProcessingJob).filter(LessonProcessingJob.id == job_id).first()
        if not job:
            raise LessonJobNotFoundError("Lesson processing job not found")
        if job.status in TERMINAL_JOB_STATUSES:
            logger.info("lesson job run_existing skipped terminal job_id=%s status=%s", job.id, job.status)
            return job
        lesson = db.query(Lesson).filter(Lesson.id == job.lesson_id, Lesson.teacher_id == job.teacher_id).first()
        if not lesson:
            logger.warning("lesson job run_existing lesson missing job_id=%s lesson_id=%s teacher_id=%s", job.id, job.lesson_id, job.teacher_id)
            self._mark_failed(db, job, "Lesson not found")
            return job
        request = self._request_from_job(job)
        await self.run_job(db, lesson=lesson, job=job, request=request)
        db.refresh(job)
        return job

    async def run_job(self, db: Session, *, lesson: Lesson, job: LessonProcessingJob, request: LessonProcessingJobCreate) -> LessonProcessingJob:
        logger.info("lesson job run started job_id=%s lesson_id=%s job_type=%s", job.id, lesson.id, request.job_type)
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
            logger.info("lesson job run completed job_id=%s lesson_id=%s job_type=%s document_count=%s transcript_id=%s", job.id, lesson.id, job.job_type, len(job.document_ids or []), job.transcript_id)
        except Exception as exc:
            logger.exception("lesson job run failed job_id=%s lesson_id=%s job_type=%s error_type=%s", job.id, lesson.id, job.job_type, type(exc).__name__)
            self._mark_failed(db, job, str(exc) or "Lesson processing job failed")
        return job

    def _request_from_job(self, job: LessonProcessingJob) -> LessonProcessingJobCreate:
        return LessonProcessingJobCreate(
            job_type=job.job_type,
            recording_id=job.recording_id,
            transcript_id=job.transcript_id,
            document_types=list(job.document_types or []),
        )

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
        logger.info("lesson job marked running job_id=%s stage=%s attempts=%s", job.id, job.stage, job.attempts)

    def _mark_stage(self, db: Session, job: LessonProcessingJob, *, stage: str) -> None:
        job.stage = stage
        job.updated_at = utc_now()
        db.commit()
        db.refresh(job)
        logger.info("lesson job stage changed job_id=%s stage=%s", job.id, stage)

    def _mark_completed(self, db: Session, job: LessonProcessingJob) -> None:
        now = utc_now()
        job.status = "completed"
        job.stage = "completed"
        job.finished_at = now
        job.updated_at = now
        job.error_message = None
        db.commit()
        db.refresh(job)
        logger.info("lesson job marked completed job_id=%s finished_at=%s", job.id, job.finished_at)

    def _mark_failed(self, db: Session, job: LessonProcessingJob, message: str) -> None:
        now = utc_now()
        job.status = "failed"
        job.stage = "failed"
        job.finished_at = now
        job.updated_at = now
        job.error_message = " ".join(message.split())[:500]
        db.commit()
        db.refresh(job)
        logger.warning("lesson job marked failed job_id=%s message_chars=%s", job.id, len(job.error_message or ""))

    async def _run_transcription_stage(
        self,
        db: Session,
        *,
        lesson: Lesson,
        job: LessonProcessingJob,
        recording_id: str | None,
    ) -> LessonTranscript:
        logger.info("lesson job transcription stage started job_id=%s lesson_id=%s recording_id=%s", job.id, lesson.id, recording_id)
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
            logger.warning("lesson job transcription stage failed job_id=%s transcript_id=%s status=%s", job.id, transcript.id, transcript.status)
            raise RecordingNotFoundError(transcript.error_message or "Transcription failed")
        logger.info("lesson job transcription stage completed job_id=%s transcript_id=%s recording_id=%s", job.id, transcript.id, transcript.recording_id)
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
        logger.info("lesson job document stage started job_id=%s lesson_id=%s transcript_id=%s requested_types=%s", job.id, lesson.id, transcript_id, document_types)
        self._mark_stage(db, job, stage="generating_documents")
        if transcript_id and not self._transcript_exists(db, lesson=lesson, transcript_id=transcript_id):
            raise LessonTranscriptNotFoundError("Completed lesson transcript not found")
        requested_types = document_types or list(DOCUMENT_TYPES)
        existing_documents = self.document_service.list_documents(db, lesson=lesson)
        documents_by_type = {document.document_type: document for document in existing_documents if document.status == "completed"}
        missing_types = [document_type for document_type in requested_types if document_type not in documents_by_type]

        generated_documents: list[LessonGeneratedDocument] = []
        logger.info("lesson job document stage planned job_id=%s requested_types=%s existing_types=%s missing_types=%s", job.id, requested_types, sorted(documents_by_type), missing_types)
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
        logger.info("lesson job document stage completed job_id=%s document_ids=%s transcript_id=%s", job.id, job.document_ids, job.transcript_id)
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


async def run_lesson_processing_job_once(job_id: str) -> None:
    """Run one persisted lesson processing job using a fresh database session.

    This is suitable for FastAPI BackgroundTasks today and for external worker
    entrypoints later because it receives only the persisted job id.
    """

    logger.info("lesson background job runner opening db session job_id=%s", job_id)
    db = SessionLocal()
    try:
        await LessonProcessingJobService().run_existing_job(db, job_id=job_id)
    finally:
        db.close()
        logger.info("lesson background job runner closed db session job_id=%s", job_id)
