from collections import defaultdict, deque
import json
import logging
import math
import time

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.schemas import (
    GenerationPresetResponse,
    GenerationPromptResponse,
    GenerationProviderStatusResponse,
    GenerationRequest,
    GenerationHistoryResponse,
    GenerationJobResponse,
    GenerationResultResponse,
    GenerationValidationRequest,
    GenerationValidationResponse,
)
from app.config import settings
from app.database import get_db
from app.services.ai_generation import AIGenerationError, AIGenerationService
from app.services.latex_compiler import LatexCompiler
from app.services.latex_validator import validate_latex_document
from app.services.generation_history_service import GenerationHistoryNotFoundError, GenerationHistoryService
from app.services.generation_jobs import GenerationJobNotFoundError, GenerationJobService
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
rate_limit_buckets: dict[str, deque[float]] = defaultdict(deque)
active_generation_requests: dict[str, float] = {}
GENERATION_DUPLICATE_RETRY_AFTER_SECONDS = 3

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
    if key in active_generation_requests:
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
        )
    active_generation_requests[key] = time.monotonic()
    return key


def finish_generation_request(key: str | None) -> None:
    if key:
        active_generation_requests.pop(key, None)


def enforce_ai_rate_limit(request: Request) -> None:
    limit = settings.AI_RATE_LIMIT_PER_MINUTE
    if limit <= 0:
        return

    client = get_request_client(request)
    key = f"{client}:{request.url.path}"
    now = time.monotonic()
    bucket = rate_limit_buckets[key]
    while bucket and now - bucket[0] >= 60:
        bucket.popleft()
    if len(bucket) >= limit:
        retry_after = max(1, math.ceil(60 - (now - bucket[0])))
        logger.warning(
            "ai rate limit exceeded client=%s path=%s limit=%s window_seconds=60 retry_after_seconds=%s",
            client,
            request.url.path,
            limit,
            retry_after,
        )
        raise HTTPException(
            status_code=429,
            detail=f"AI rate limit exceeded. Try again in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )
    bucket.append(now)


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
            warnings.append("Тема не указана: нейросеть будет выбирать тему самостоятельно, что может снизить точность пособия.")
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


@router.get("/presets", response_model=list[GenerationPresetResponse])
async def list_generation_presets():
    return PRESETS


@router.post("/prompt", response_model=GenerationPromptResponse)
async def preview_generation_prompt(request: Request, generation_request: GenerationRequest):
    generation_request = prepare_generation_request(generation_request)
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
    db: Session = Depends(get_db),
):
    return generation_history_service.list_project_history(db, project_id, skip=skip, limit=limit)


@router.get("/history/item/{history_id}", response_model=GenerationHistoryResponse)
async def get_generation_history_item(history_id: str, db: Session = Depends(get_db)):
    try:
        return generation_history_service.get_history_item(db, history_id)
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
async def generate_latex(request: Request, generation_request: GenerationRequest, db: Session = Depends(get_db)):
    generation_request = prepare_generation_request(generation_request)
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
            )
        except GenerationOrchestrationError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    finally:
        finish_generation_request(active_request_key)


@router.post("/jobs", response_model=GenerationJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_generation_job(request: Request, generation_request: GenerationRequest, db: Session = Depends(get_db)):
    generation_request = prepare_generation_request(generation_request)
    active_request_key = begin_generation_request(request, generation_request)
    try:
        enforce_ai_rate_limit(request)
        request_sha = generation_request_fingerprint(generation_request)
        prompt_response = build_generation_prompt_response(generation_request)
        job = generation_job_service.create_job(
            db,
            generation_request=generation_request,
            request_hash=request_sha,
            prompt_hash=text_digest(prompt_response.prompt),
        )
        # Persist the job first; this PR runs it inline, and a later worker can reuse the same job contract.
        job = await generation_job_service.run_job(
            db,
            job=job,
            generation_request=generation_request,
            prompt_response=prompt_response,
            request_hash=request_sha,
            orchestrator=generation_orchestrator,
        )
        return generation_job_service.to_response(job)
    finally:
        finish_generation_request(active_request_key)


@router.get("/jobs/{job_id}", response_model=GenerationJobResponse)
async def get_generation_job(job_id: str, db: Session = Depends(get_db)):
    try:
        job = generation_job_service.get_job(db, job_id=job_id)
    except GenerationJobNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return generation_job_service.to_response(job)
