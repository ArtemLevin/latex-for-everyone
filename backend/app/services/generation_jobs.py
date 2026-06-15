import logging
import uuid

from sqlalchemy.orm import Session

from app.models import GenerationJob
from app.schemas import GenerationJobResponse, GenerationPromptResponse, GenerationRequest, GenerationResultResponse
from app.services.generation_orchestrator import GenerationOrchestrationError, GenerationOrchestrator, text_digest
from app.time_utils import utc_now

logger = logging.getLogger(__name__)


TERMINAL_GENERATION_JOB_STATUSES = {"completed", "failed", "canceled"}


class GenerationJobNotFoundError(ValueError):
    """Raised when a persisted generation job does not exist."""


class GenerationJobService:
    """Persistence boundary for generation jobs.

    Jobs run inline in this PR so the API contract is durable immediately; a
    later worker can call the same service methods without changing response
    shapes or frontend polling semantics.
    """

    def create_job(
        self,
        db: Session,
        *,
        generation_request: GenerationRequest,
        request_hash: str,
        owner_id: str,
        prompt_hash: str | None = None,
    ) -> GenerationJob:
        job = GenerationJob(
            id=str(uuid.uuid4()),
            project_id=generation_request.project_id,
            owner_id=owner_id,
            provider=generation_request.provider or "default",
            model=generation_request.model,
            status="queued",
            stage="queued",
            request_hash=request_hash,
            prompt_hash=prompt_hash,
            request_payload=generation_request.model_dump(mode="json"),
            attempts=0,
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        logger.info(
            "generation job queued job_id=%s project_id=%s provider=%s model=%s request_sha=%s",
            job.id,
            job.project_id,
            job.provider,
            job.model or "default",
            request_hash,
        )
        return job

    def get_job(self, db: Session, *, job_id: str, owner_id: str | None = None) -> GenerationJob:
        query = db.query(GenerationJob).filter(GenerationJob.id == job_id)
        if owner_id is not None:
            query = query.filter(GenerationJob.owner_id == owner_id)
        job = query.first()
        if not job:
            raise GenerationJobNotFoundError(f"Generation job {job_id} not found")
        return job

    async def run_job(
        self,
        db: Session,
        *,
        job: GenerationJob,
        generation_request: GenerationRequest,
        prompt_response: GenerationPromptResponse,
        request_hash: str,
        owner_id: str,
        orchestrator: GenerationOrchestrator,
    ) -> GenerationJob:
        if job.status in TERMINAL_GENERATION_JOB_STATUSES:
            logger.info("generation job run skipped terminal job_id=%s status=%s", job.id, job.status)
            return job

        self._mark_running(db, job, stage="generating")
        try:
            result = await orchestrator.generate(
                db=db,
                generation_request=generation_request,
                prompt_response=prompt_response,
                request_sha=request_hash,
                owner_id=owner_id,
            )
        except GenerationOrchestrationError as exc:
            self._mark_failed(db, job, exc.detail)
            return job
        self._mark_completed(db, job, result)
        return job

    def to_response(self, job: GenerationJob) -> GenerationJobResponse:
        result = GenerationResultResponse(**job.result_payload) if job.result_payload else None
        return GenerationJobResponse(
            id=job.id,
            project_id=job.project_id,
            provider=job.provider,
            model=job.model,
            status=job.status,
            stage=job.stage,
            request_hash=job.request_hash,
            prompt_hash=job.prompt_hash,
            result=result,
            error_message=job.error_message,
            attempts=job.attempts,
            started_at=job.started_at,
            finished_at=job.finished_at,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )

    def _mark_running(self, db: Session, job: GenerationJob, *, stage: str) -> None:
        job.status = "running"
        job.stage = stage
        job.attempts += 1
        job.started_at = job.started_at or utc_now()
        job.updated_at = utc_now()
        db.add(job)
        db.commit()
        db.refresh(job)
        logger.info("generation job running job_id=%s stage=%s attempts=%s", job.id, job.stage, job.attempts)

    def _mark_completed(self, db: Session, job: GenerationJob, result: GenerationResultResponse) -> None:
        job.status = "completed"
        job.stage = "completed"
        job.result_payload = result.model_dump(mode="json")
        job.prompt_hash = job.prompt_hash or text_digest(result.prompt)
        job.error_message = None
        job.finished_at = utc_now()
        job.updated_at = utc_now()
        db.add(job)
        db.commit()
        db.refresh(job)
        logger.info("generation job completed job_id=%s provider=%s model=%s", job.id, result.provider, result.model)

    def _mark_failed(self, db: Session, job: GenerationJob, message: str) -> None:
        job.status = "failed"
        job.stage = "failed"
        job.error_message = message
        job.finished_at = utc_now()
        job.updated_at = utc_now()
        db.add(job)
        db.commit()
        db.refresh(job)
        logger.warning("generation job failed job_id=%s error=%s", job.id, message)
