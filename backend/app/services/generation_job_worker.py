import asyncio
import logging
import os
import socket
import uuid

from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import GenerationJob
from app.schemas import GenerationPromptResponse, GenerationRequest
from app.services.ai_generation import AIGenerationService
from app.services.generation_history_service import GenerationHistoryService
from app.services.generation_job_queue import GenerationJobQueueService
from app.services.generation_jobs import GenerationJobNotFoundError, GenerationJobService
from app.services.generation_orchestrator import GenerationOrchestrator, text_digest
from app.services.latex_compiler import LatexCompiler
from app.services.prompt_builder import build_latex_generation_prompt

logger = logging.getLogger(__name__)

ai_generator = AIGenerationService()
generation_compiler = LatexCompiler()
generation_history_service = GenerationHistoryService()
generation_job_service = GenerationJobService()
generation_job_queue_service = GenerationJobQueueService()
generation_orchestrator = GenerationOrchestrator(
    ai_generator=ai_generator,
    compiler=generation_compiler,
    history_service=generation_history_service,
)


def default_worker_id() -> str:
    configured = settings.AI_GENERATION_JOB_WORKER_ID
    if configured:
        return configured
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


def build_prompt_response_from_job(job: GenerationJob) -> tuple[GenerationRequest, GenerationPromptResponse]:
    generation_request = GenerationRequest(**job.request_payload)
    prompt = build_latex_generation_prompt(generation_request.fields, generation_request.materials)
    return generation_request, GenerationPromptResponse(
        status="success",
        prompt=prompt,
        warnings=[],
        provider=generation_request.provider,
        model=generation_request.model,
    )


async def run_claimed_generation_job(
    *,
    job_id: str,
    worker_id: str,
    db: Session | None = None,
    timeout_seconds: int | None = None,
) -> GenerationJob | None:
    owns_session = db is None
    session = db or SessionLocal()
    try:
        try:
            job = generation_job_service.get_job(session, job_id=job_id)
        except GenerationJobNotFoundError:
            logger.warning("generation worker claimed job missing job_id=%s worker_id=%s", job_id, worker_id)
            return None
        if job.status == "canceled":
            logger.info("generation worker skips canceled claimed job_id=%s worker_id=%s", job.id, worker_id)
            return job
        if job.status != "running" or job.worker_id != worker_id:
            logger.info(
                "generation worker skips unowned/non-running job_id=%s worker_id=%s status=%s job_worker_id=%s",
                job.id,
                worker_id,
                job.status,
                job.worker_id or "-",
            )
            return job

        generation_request, prompt_response = build_prompt_response_from_job(job)
        generation_job_queue_service.heartbeat(session, job_id=job.id, worker_id=worker_id)
        logger.info(
            "generation worker running job_id=%s worker_id=%s owner_id=%s project_id=%s request_sha=%s prompt_sha=%s",
            job.id,
            worker_id,
            job.owner_id,
            job.project_id or "-",
            job.request_hash,
            job.prompt_hash or text_digest(prompt_response.prompt),
        )
        return await generation_job_service.run_job(
            session,
            job=job,
            generation_request=generation_request,
            prompt_response=prompt_response,
            request_hash=job.request_hash,
            owner_id=job.owner_id,
            orchestrator=generation_orchestrator,
            timeout_seconds=timeout_seconds
            if timeout_seconds is not None
            else settings.AI_GENERATION_JOB_TIMEOUT_SECONDS,
            mark_running=False,
        )
    finally:
        if owns_session:
            session.close()


async def run_generation_job_once(
    *,
    db: Session | None = None,
    job_id: str | None = None,
    owner_id: str | None = None,
    worker_id: str | None = None,
    timeout_seconds: int | None = None,
) -> GenerationJob | None:
    owns_session = db is None
    session = db or SessionLocal()
    resolved_worker_id = worker_id or default_worker_id()
    try:
        if job_id:
            try:
                job = generation_job_service.get_job(session, job_id=job_id, owner_id=owner_id)
            except GenerationJobNotFoundError:
                logger.warning("generation worker job missing job_id=%s owner_id=%s", job_id, owner_id or "-")
                return None
            if job.status != "queued":
                logger.info("generation worker skipped non-queued job_id=%s status=%s", job.id, job.status)
                return job
            claimed = generation_job_queue_service.claim_job_by_id(
                session, worker_id=resolved_worker_id, owner_id=owner_id, job_id=job.id
            )
            if claimed is None:
                return None
            job = claimed
        else:
            job = generation_job_queue_service.claim_next_job(session, worker_id=resolved_worker_id, owner_id=owner_id)
            if job is None:
                logger.debug("generation worker idle owner_id=%s worker_id=%s", owner_id or "-", resolved_worker_id)
                return None

        return await run_claimed_generation_job(
            db=session,
            job_id=job.id,
            worker_id=resolved_worker_id,
            timeout_seconds=timeout_seconds,
        )
    finally:
        if owns_session:
            session.close()


def recover_stale_generation_jobs(
    *,
    db: Session | None = None,
    owner_id: str | None = None,
    stale_after_seconds: int | None = None,
    limit: int = 100,
) -> int:
    owns_session = db is None
    session = db or SessionLocal()
    threshold = (
        stale_after_seconds if stale_after_seconds is not None else settings.AI_GENERATION_JOB_STALE_AFTER_SECONDS
    )
    try:
        recovered = generation_job_service.recover_stale_running_jobs(
            session,
            stale_after_seconds=threshold,
            owner_id=owner_id,
            limit=limit,
        )
        if recovered:
            logger.warning(
                "generation worker recovered stale jobs count=%s owner_id=%s", len(recovered), owner_id or "-"
            )
        return len(recovered)
    finally:
        if owns_session:
            session.close()


async def run_generation_worker_loop(
    *,
    poll_interval_seconds: float | None = None,
    max_jobs: int = 0,
    owner_id: str | None = None,
    worker_id: str | None = None,
    timeout_seconds: int | None = None,
    stale_after_seconds: int | None = None,
) -> int:
    processed = 0
    resolved_worker_id = worker_id or default_worker_id()
    interval = settings.AI_GENERATION_JOB_IDLE_SLEEP_SECONDS if poll_interval_seconds is None else poll_interval_seconds
    logger.info(
        "generation worker loop started worker_id=%s owner_id=%s poll_interval_seconds=%s max_jobs=%s",
        resolved_worker_id,
        owner_id or "-",
        interval,
        max_jobs,
    )
    while True:
        recover_stale_generation_jobs(owner_id=owner_id, stale_after_seconds=stale_after_seconds)
        job = await run_generation_job_once(
            owner_id=owner_id,
            worker_id=resolved_worker_id,
            timeout_seconds=timeout_seconds,
        )
        if job and job.status in {"completed", "failed", "canceled"}:
            processed += 1
        if max_jobs > 0 and processed >= max_jobs:
            break
        if job is None:
            await asyncio.sleep(interval)
    logger.info("generation worker loop stopped worker_id=%s processed=%s", resolved_worker_id, processed)
    return processed
