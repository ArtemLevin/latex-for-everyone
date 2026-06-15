import asyncio
import logging

from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import GenerationJob
from app.schemas import GenerationPromptResponse, GenerationRequest
from app.services.ai_generation import AIGenerationService
from app.services.generation_history_service import GenerationHistoryService
from app.services.generation_jobs import GenerationJobNotFoundError, GenerationJobService
from app.services.generation_orchestrator import GenerationOrchestrator, text_digest
from app.services.latex_compiler import LatexCompiler
from app.services.prompt_builder import build_latex_generation_prompt

logger = logging.getLogger(__name__)

ai_generator = AIGenerationService()
generation_compiler = LatexCompiler()
generation_history_service = GenerationHistoryService()
generation_job_service = GenerationJobService()
generation_orchestrator = GenerationOrchestrator(
    ai_generator=ai_generator,
    compiler=generation_compiler,
    history_service=generation_history_service,
)


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


async def run_generation_job_once(
    *,
    db: Session | None = None,
    job_id: str | None = None,
    owner_id: str | None = None,
    timeout_seconds: int | None = None,
) -> GenerationJob | None:
    owns_session = db is None
    session = db or SessionLocal()
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
        else:
            job = generation_job_service.get_next_queued_job(session, owner_id=owner_id)
            if job is None:
                logger.debug("generation worker idle owner_id=%s", owner_id or "-")
                return None

        generation_request, prompt_response = build_prompt_response_from_job(job)
        logger.info(
            "generation worker claimed job_id=%s owner_id=%s project_id=%s request_sha=%s prompt_sha=%s",
            job.id,
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
            timeout_seconds=timeout_seconds if timeout_seconds is not None else settings.AI_GENERATION_JOB_TIMEOUT_SECONDS,
        )
    finally:
        if owns_session:
            session.close()


async def run_generation_worker_loop(
    *,
    poll_interval_seconds: float = 2.0,
    max_jobs: int = 0,
    owner_id: str | None = None,
    timeout_seconds: int | None = None,
) -> int:
    processed = 0
    logger.info(
        "generation worker loop started owner_id=%s poll_interval_seconds=%s max_jobs=%s",
        owner_id or "-",
        poll_interval_seconds,
        max_jobs,
    )
    while True:
        job = await run_generation_job_once(owner_id=owner_id, timeout_seconds=timeout_seconds)
        if job and job.status != "queued":
            processed += 1
        if max_jobs > 0 and processed >= max_jobs:
            break
        if job is None:
            await asyncio.sleep(poll_interval_seconds)
    logger.info("generation worker loop stopped processed=%s", processed)
    return processed
