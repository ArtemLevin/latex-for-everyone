import asyncio
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

    The service supports both inline execution and background dispatch; routers
    decide when to schedule work while this class owns status transitions.
    """

    def create_job(
        self,
        db: Session,
        *,
        generation_request: GenerationRequest,
        request_hash: str,
        owner_id: str,
        prompt_hash: str | None = None,
        idempotency_key: str | None = None,
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
            idempotency_key=idempotency_key,
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

    def get_job_by_idempotency_key(self, db: Session, *, owner_id: str, idempotency_key: str) -> GenerationJob | None:
        return (
            db.query(GenerationJob)
            .filter(GenerationJob.owner_id == owner_id, GenerationJob.idempotency_key == idempotency_key)
            .order_by(GenerationJob.created_at.desc())
            .first()
        )

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
        timeout_seconds: int = 0,
    ) -> GenerationJob:
        if job.status in TERMINAL_GENERATION_JOB_STATUSES:
            logger.info("generation job run skipped terminal job_id=%s status=%s", job.id, job.status)
            return job

        self._mark_running(db, job, stage="generating")
        try:
            generate_coro = orchestrator.generate(
                db=db,
                generation_request=generation_request,
                prompt_response=prompt_response,
                request_sha=request_hash,
                owner_id=owner_id,
            )
            # Timeout is enforced at the persisted-job boundary so both inline
            # and background execution modes return the same failure state.
            if timeout_seconds > 0:
                result = await asyncio.wait_for(generate_coro, timeout=timeout_seconds)
            else:
                result = await generate_coro
        except asyncio.TimeoutError:
            self._mark_failed(db, job, "AI generation job timed out.")
            return job
        except GenerationOrchestrationError as exc:
            self._mark_failed(db, job, exc.detail)
            return job

        db.refresh(job)
        if job.status == "canceled":
            logger.info("generation job completion skipped because job was canceled job_id=%s", job.id)
            return job
        self._mark_completed(db, job, result)
        return job


    def cancel_job(self, db: Session, *, job_id: str, owner_id: str) -> GenerationJob:
        job = self.get_job(db, job_id=job_id, owner_id=owner_id)
        if job.status in TERMINAL_GENERATION_JOB_STATUSES:
            logger.info("generation job cancel ignored terminal job_id=%s status=%s", job.id, job.status)
            return job
        job.status = "canceled"
        job.stage = "canceled"
        job.error_message = "Generation job was canceled by user request."
        job.finished_at = utc_now()
        job.updated_at = utc_now()
        db.add(job)
        db.commit()
        db.refresh(job)
        logger.info("generation job canceled job_id=%s owner_id=%s", job.id, owner_id)
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
            idempotency_key=job.idempotency_key,
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
