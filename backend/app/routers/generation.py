import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.schemas import (
    GenerationPresetResponse,
    GenerationPromptResponse,
    GenerationProviderStatusResponse,
    GenerationRequest,
    GenerationHistoryResponse,
    GenerationJobOperatorStatusResponse,
    GenerationJobRecoverStaleRequest,
    GenerationJobRecoverStaleResponse,
    GenerationJobResponse,
    GenerationJobStaleSampleResponse,
    GenerationResultResponse,
    GenerationValidationRequest,
    GenerationValidationResponse,
)
from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user_id
from app.models import Project
from app.services.ai_generation import AIGenerationError, AIGenerationService
from app.services.ai_request_control import (
    DuplicateRequestError,
    InvalidIdempotencyKeyError,
    RequestControlBackendError,
    build_ai_request_control_service,
)
from app.services.latex_compiler import LatexCompiler
from app.services.latex_validator import validate_latex_document
from app.services.generation_history_service import GenerationHistoryNotFoundError, GenerationHistoryService
from app.services.generation_jobs import GenerationJobNotFoundError, GenerationJobRetryError, GenerationJobService
from app.services.prompt_builder import build_latex_generation_prompt
from app.services.generation_orchestrator import (
    GenerationOrchestrationError,
    GenerationOrchestrator,
    provider_error_detail,
    text_digest,
)

logger = logging.getLogger(__name__)

router = APIRouter()

ai_generator = AIGenerationService()
generation_compiler = LatexCompiler()
generation_history_service = GenerationHistoryService()
generation_job_service = GenerationJobService()
generation_orchestrator = GenerationOrchestrator(
    ai_generator=ai_generator,
    compiler=generation_compiler,
    history_service=generation_history_service,
)
request_control_service = build_ai_request_control_service()
# Backwards-compatible aliases keep existing tests focused on endpoint behavior while router code uses the service boundary.
rate_limit_buckets = getattr(request_control_service.rate_limiter, "buckets", {})
active_generation_requests = getattr(request_control_service.in_flight, "active_requests", {})
GENERATION_DUPLICATE_RETRY_AFTER_SECONDS = settings.AI_DUPLICATE_RETRY_AFTER_SECONDS

PRESETS: list[GenerationPresetResponse] = [
    GenerationPresetResponse(
        id="ege_math_11_hard",
        name="ЕГЭ математика, 11 класс, сложные задачи",
        description="Базовый сценарий для обучающего пособия ЕГЭ по математике с одной сложной тренировочной задачей.",
        defaults={
            "level": "ЕГЭ",
            "language": "русский",
            "content_source_mode": "materials_only",
            "latex_mode": "safe",
            "alpha_code": 1,
            "beta_code": 1,
            "gamma_code": 4,
            "grade": "11 класс",
            "subject": "математика",
            "priority_method": "нейросеть выбирает самостоятельно по отношению к уровню и классу",
            "graph_analytic": "по ситуации",
        },
    )
]


def get_request_client(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def generation_request_fingerprint(generation_request: GenerationRequest) -> str:
    payload = generation_request.model_dump(mode="json")
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return text_digest(serialized)


def get_generation_duplicate_key(request: Request, generation_request: GenerationRequest) -> str:
    return f"{get_request_client(request)}:{request.url.path}:{generation_request_fingerprint(generation_request)}"


def begin_generation_request(request: Request, generation_request: GenerationRequest) -> str:
    key = get_generation_duplicate_key(request, generation_request)
    try:
        request_control_service.begin_in_flight(key)
    except DuplicateRequestError as exc:
        logger.warning(
            "ai duplicate generation submit rejected client=%s path=%s request_sha=%s materials_chars=%s topic=%s retry_after_seconds=%s",
            get_request_client(request),
            request.url.path,
            generation_request_fingerprint(generation_request),
            len(generation_request.materials),
            generation_request.fields.topic or "-",
            GENERATION_DUPLICATE_RETRY_AFTER_SECONDS,
        )
        raise HTTPException(
            status_code=409,
            detail="AI generation is already running for the same input. Wait for the current request to finish.",
            headers={"Retry-After": str(GENERATION_DUPLICATE_RETRY_AFTER_SECONDS)},
        ) from exc
    except RequestControlBackendError as exc:
        logger.exception("ai request-control backend failed during duplicate guard")
        raise HTTPException(status_code=503, detail="AI request control is temporarily unavailable.") from exc
    return key


def finish_generation_request(key: str | None) -> None:
    try:
        request_control_service.finish_in_flight(key)
    except RequestControlBackendError:
        # The request is already ending; log cleanup failures so operators can inspect Redis health.
        logger.exception("ai request-control backend failed during in-flight cleanup")


def enforce_ai_rate_limit(request: Request) -> None:
    limit = settings.AI_RATE_LIMIT_PER_MINUTE
    client = get_request_client(request)
    try:
        decision = request_control_service.check_rate_limit(key=f"{client}:{request.url.path}", limit=limit)
    except RequestControlBackendError as exc:
        logger.exception("ai request-control backend failed during rate-limit check")
        raise HTTPException(status_code=503, detail="AI request control is temporarily unavailable.") from exc
    if not decision.allowed:
        logger.warning(
            "ai rate limit exceeded client=%s path=%s limit=%s window_seconds=60 retry_after_seconds=%s",
            client,
            request.url.path,
            limit,
            decision.retry_after_seconds,
        )
        raise HTTPException(
            status_code=429,
            detail=f"AI rate limit exceeded. Try again in {decision.retry_after_seconds} seconds.",
            headers={"Retry-After": str(decision.retry_after_seconds)},
        )


def get_idempotency_key(request: Request) -> str | None:
    try:
        return request_control_service.normalize_idempotency_key(
            request.headers.get(settings.AI_IDEMPOTENCY_HEADER),
            max_chars=settings.AI_IDEMPOTENCY_KEY_MAX_CHARS,
        )
    except InvalidIdempotencyKeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def enforce_text_limit(label: str, value: str, max_chars: int) -> None:
    if max_chars > 0 and len(value) > max_chars:
        logger.warning(
            "ai text limit exceeded label=%s length=%s max_chars=%s",
            label,
            len(value),
            max_chars,
        )
        raise HTTPException(
            status_code=413,
            detail=f"{label} exceeds {max_chars} characters.",
        )


def normalize_generation_materials(materials: str) -> str:
    # Preserve meaningful line breaks while making pasted Windows/macOS text deterministic for limits and hashing.
    return materials.replace("\r\n", "\n").replace("\r", "\n").strip()


def reject_unsupported_materials_control_chars(materials: str) -> None:
    unsupported = sorted({ord(char) for char in materials if ord(char) < 32 and char not in {"\n", "\t"}})
    if unsupported:
        logger.warning(
            "ai materials rejected unsupported_control_chars count=%s codes=%s",
            len(unsupported),
            unsupported[:8],
        )
        raise HTTPException(
            status_code=422,
            detail="materials contain unsupported control characters; keep only printable text, tabs, and line breaks.",
        )


def prepare_generation_request(generation_request: GenerationRequest) -> GenerationRequest:
    normalized_materials = normalize_generation_materials(generation_request.materials)
    reject_unsupported_materials_control_chars(normalized_materials)
    enforce_text_limit("materials", normalized_materials, settings.AI_MAX_MATERIALS_CHARS)
    if normalized_materials == generation_request.materials:
        return generation_request
    return generation_request.model_copy(update={"materials": normalized_materials})


def build_generation_prompt_response(request: GenerationRequest) -> GenerationPromptResponse:
    request = prepare_generation_request(request)
    prompt = build_latex_generation_prompt(request.fields, request.materials)
    enforce_text_limit("prompt", prompt, settings.AI_MAX_PROMPT_CHARS)
    warnings = []
    if not request.fields.topic:
        if request.fields.content_source_mode == "materials_only":
            warnings.append("Тема не указана: prompt потребует определить тему по материалам без домыслов.")
        else:
            warnings.append(
                "Тема не указана: нейросеть будет выбирать тему самостоятельно, что может снизить точность пособия."
            )
    if not request.materials.strip() and request.fields.content_source_mode == "materials_only":
        warnings.append("Материалы не переданы: prompt запрещает домысливать исходные задания.")

    logger.info(
        "ai prompt built provider=%s model=%s topic=%s materials_chars=%s materials_lines=%s materials_sha=%s prompt_chars=%s prompt_sha=%s warnings=%s",
        request.provider or "default",
        request.model or "default",
        request.fields.topic or "-",
        len(request.materials),
        request.materials.count("\n") + 1 if request.materials else 0,
        text_digest(request.materials) if request.materials else "-",
        len(prompt),
        text_digest(prompt),
        len(warnings),
    )

    return GenerationPromptResponse(
        status="success",
        prompt=prompt,
        warnings=warnings,
        provider=request.provider,
        model=request.model,
    )


def ensure_project_access(db: Session, *, project_id: str | None, owner_id: str) -> None:
    if project_id is None:
        return
    project = db.query(Project).filter(Project.id == project_id, Project.owner_id == owner_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")


@router.get("/presets", response_model=list[GenerationPresetResponse])
async def list_generation_presets():
    return PRESETS


@router.post("/prompt", response_model=GenerationPromptResponse)
async def preview_generation_prompt(
    request: Request,
    generation_request: GenerationRequest,
    owner_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    generation_request = prepare_generation_request(generation_request)
    ensure_project_access(db, project_id=generation_request.project_id, owner_id=owner_id)
    enforce_ai_rate_limit(request)
    logger.info(
        "ai prompt preview requested provider=%s model=%s topic=%s materials_chars=%s",
        generation_request.provider or "default",
        generation_request.model or "default",
        generation_request.fields.topic or "-",
        len(generation_request.materials),
    )
    return build_generation_prompt_response(generation_request)


@router.get("/history/project/{project_id}", response_model=list[GenerationHistoryResponse])
async def list_generation_history_for_project(
    project_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    owner_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    ensure_project_access(db, project_id=project_id, owner_id=owner_id)
    return generation_history_service.list_project_history(db, project_id, owner_id=owner_id, skip=skip, limit=limit)


@router.get("/history/item/{history_id}", response_model=GenerationHistoryResponse)
async def get_generation_history_item(
    history_id: str,
    owner_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    try:
        return generation_history_service.get_history_item(db, history_id, owner_id=owner_id)
    except GenerationHistoryNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/providers/status", response_model=GenerationProviderStatusResponse)
async def get_generation_provider_status(
    request: Request,
    provider: str | None = Query(default=None),
    model: str | None = Query(default=None),
):
    enforce_ai_rate_limit(request)
    logger.info("ai provider status requested provider=%s model=%s", provider or "default", model or "default")
    try:
        status = await ai_generator.get_provider_status(provider=provider, model=model)
    except AIGenerationError as exc:
        logger.warning(
            "ai provider status failed provider=%s model=%s status_code=%s error=%s",
            provider or "default",
            model or "default",
            exc.status_code,
            exc,
        )
        raise HTTPException(status_code=exc.status_code, detail=provider_error_detail(exc)) from exc
    logger.info(
        "ai provider status completed provider=%s model=%s available=%s model_available=%s models_count=%s",
        status.get("provider"),
        status.get("model"),
        status.get("available"),
        status.get("model_available"),
        len(status.get("models") or []),
    )
    return GenerationProviderStatusResponse(**status)


@router.post("/validate", response_model=GenerationValidationResponse)
async def validate_generated_latex(request: Request, validation_request: GenerationValidationRequest):
    enforce_ai_rate_limit(request)
    enforce_text_limit("latex_code", validation_request.latex_code, settings.AI_MAX_RAW_OUTPUT_CHARS)
    validation = validate_latex_document(validation_request.latex_code)
    logger.info(
        "ai latex validation completed latex_chars=%s latex_sha=%s valid=%s errors=%s warnings=%s",
        len(validation_request.latex_code),
        text_digest(validation_request.latex_code),
        validation["valid"],
        len(validation["errors"]),
        len(validation["warnings"]),
    )
    return GenerationValidationResponse(**validation)


@router.post("/generate", response_model=GenerationResultResponse)
async def generate_latex(
    request: Request,
    generation_request: GenerationRequest,
    owner_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    generation_request = prepare_generation_request(generation_request)
    ensure_project_access(db, project_id=generation_request.project_id, owner_id=owner_id)
    active_request_key = begin_generation_request(request, generation_request)
    try:
        enforce_ai_rate_limit(request)
        request_sha = generation_request_fingerprint(generation_request)
        logger.info(
            "ai generation requested provider=%s model=%s topic=%s materials_chars=%s request_sha=%s",
            generation_request.provider or "default",
            generation_request.model or "default",
            generation_request.fields.topic or "-",
            len(generation_request.materials),
            request_sha,
        )
        prompt_response = build_generation_prompt_response(generation_request)
        try:
            return await generation_orchestrator.generate(
                db=db,
                generation_request=generation_request,
                prompt_response=prompt_response,
                request_sha=request_sha,
                owner_id=owner_id,
            )
        except GenerationOrchestrationError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    finally:
        finish_generation_request(active_request_key)


@router.post("/jobs", response_model=GenerationJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_generation_job(
    request: Request,
    generation_request: GenerationRequest,
    response: Response,
    owner_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    generation_request = prepare_generation_request(generation_request)
    ensure_project_access(db, project_id=generation_request.project_id, owner_id=owner_id)
    request_sha = generation_request_fingerprint(generation_request)
    idempotency_key = get_idempotency_key(request)
    if idempotency_key:
        existing_job = generation_job_service.get_job_by_idempotency_key(
            db,
            owner_id=owner_id,
            idempotency_key=idempotency_key,
        )
        if existing_job:
            if existing_job.request_hash != request_sha:
                raise HTTPException(
                    status_code=409, detail="Idempotency key was already used for a different generation request."
                )
            logger.info(
                "generation job idempotency replay job_id=%s owner_id=%s request_sha=%s",
                existing_job.id,
                owner_id,
                request_sha,
            )
            response.headers["Location"] = f"/api/generation/jobs/{existing_job.id}"
            return generation_job_service.to_response(existing_job)
    else:
        active_job = generation_job_service.get_active_job_by_request_hash(
            db, owner_id=owner_id, request_hash=request_sha
        )
        if active_job is not None:
            raise HTTPException(
                status_code=409,
                detail="Generation job is already queued or running for the same input.",
                headers={"Retry-After": str(GENERATION_DUPLICATE_RETRY_AFTER_SECONDS)},
            )

    enforce_ai_rate_limit(request)
    prompt_response = build_generation_prompt_response(generation_request)
    job = generation_job_service.create_job(
        db,
        generation_request=generation_request,
        request_hash=request_sha,
        prompt_hash=text_digest(prompt_response.prompt),
        owner_id=owner_id,
        idempotency_key=idempotency_key,
    )
    response.headers["Location"] = f"/api/generation/jobs/{job.id}"
    logger.info("generation job enqueued job_id=%s owner_id=%s request_sha=%s", job.id, owner_id, request_sha)
    return generation_job_service.to_response(job)


@router.get("/jobs", response_model=list[GenerationJobResponse])
async def list_generation_jobs(
    project_id: str | None = Query(default=None),
    job_status: str | None = Query(default=None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    owner_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    ensure_project_access(db, project_id=project_id, owner_id=owner_id)
    jobs = generation_job_service.list_jobs(
        db,
        owner_id=owner_id,
        project_id=project_id,
        status=job_status,
        skip=skip,
        limit=limit,
    )
    return [generation_job_service.to_response(job) for job in jobs]


@router.get("/jobs/operator/status", response_model=GenerationJobOperatorStatusResponse)
async def get_generation_jobs_operator_status(
    stale_sample_limit: int = Query(10, ge=0, le=50),
    owner_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    summary = generation_job_service.get_operator_status(
        db,
        owner_id=owner_id,
        stale_after_seconds=settings.AI_GENERATION_JOB_STALE_AFTER_SECONDS,
        stale_sample_limit=stale_sample_limit,
    )
    return GenerationJobOperatorStatusResponse(
        execution_mode=settings.AI_GENERATION_JOB_EXECUTION_MODE,
        stale_after_seconds=settings.AI_GENERATION_JOB_STALE_AFTER_SECONDS,
        counts=summary["counts"],
        backlog=summary["backlog"],
        stale_running=summary["stale_running"],
        stale_samples=[
            GenerationJobStaleSampleResponse(
                id=job.id,
                project_id=job.project_id,
                status=job.status,
                stage=job.stage,
                attempts=job.attempts,
                worker_id=job.worker_id,
                locked_at=job.locked_at,
                heartbeat_at=job.heartbeat_at,
                started_at=job.started_at,
                updated_at=job.updated_at,
            )
            for job in summary["stale_samples"]
        ],
    )


@router.post("/jobs/operator/recover-stale", response_model=GenerationJobRecoverStaleResponse)
async def recover_stale_generation_jobs(
    request_body: GenerationJobRecoverStaleRequest = GenerationJobRecoverStaleRequest(),
    owner_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    stale_after_seconds = (
        request_body.stale_after_seconds
        if request_body.stale_after_seconds is not None
        else settings.AI_GENERATION_JOB_STALE_AFTER_SECONDS
    )
    recovered = generation_job_service.recover_stale_running_jobs(
        db,
        stale_after_seconds=stale_after_seconds,
        owner_id=owner_id,
        limit=request_body.limit,
    )
    logger.warning(
        "generation operator recovered stale jobs owner_id=%s count=%s stale_after_seconds=%s",
        owner_id,
        len(recovered),
        stale_after_seconds,
    )
    return GenerationJobRecoverStaleResponse(
        recovered_count=len(recovered),
        recovered_job_ids=[job.id for job in recovered],
        stale_after_seconds=stale_after_seconds,
    )


@router.get("/jobs/{job_id}", response_model=GenerationJobResponse)
async def get_generation_job(
    job_id: str,
    owner_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    try:
        job = generation_job_service.get_job(db, job_id=job_id, owner_id=owner_id)
    except GenerationJobNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return generation_job_service.to_response(job)


@router.post("/jobs/{job_id}/retry", response_model=GenerationJobResponse)
async def retry_generation_job(
    request: Request,
    job_id: str,
    response: Response,
    owner_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    enforce_ai_rate_limit(request)
    try:
        job = generation_job_service.retry_job(db, job_id=job_id, owner_id=owner_id)
    except GenerationJobRetryError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except GenerationJobNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    response.headers["Location"] = f"/api/generation/jobs/{job.id}"
    logger.info("generation job retry requeued job_id=%s owner_id=%s", job.id, owner_id)
    return generation_job_service.to_response(job)


@router.post("/jobs/{job_id}/cancel", response_model=GenerationJobResponse)
async def cancel_generation_job(
    job_id: str,
    owner_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    try:
        job = generation_job_service.cancel_job(db, job_id=job_id, owner_id=owner_id)
    except GenerationJobNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return generation_job_service.to_response(job)
