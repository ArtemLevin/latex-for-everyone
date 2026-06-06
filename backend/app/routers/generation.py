from collections import defaultdict, deque
import hashlib
import logging
import time

from fastapi import APIRouter, HTTPException, Query, Request

from app.schemas import (
    GenerationPresetResponse,
    GenerationPromptResponse,
    GenerationProviderStatusResponse,
    GenerationRequest,
    GenerationResultResponse,
    GenerationValidationRequest,
    GenerationValidationResponse,
)
from app.config import settings
from app.services.ai_generation import AIGenerationError, AIGenerationService, extract_latex_code
from app.services.latex_document_builder import build_latex_document
from app.services.latex_validator import validate_latex_document
from app.services.prompt_builder import build_latex_generation_prompt

logger = logging.getLogger(__name__)

router = APIRouter()

ai_generator = AIGenerationService()
rate_limit_buckets: dict[str, deque[float]] = defaultdict(deque)

PRESETS: list[GenerationPresetResponse] = [
    GenerationPresetResponse(
        id="ege_math_11_hard",
        name="ЕГЭ математика, 11 класс, сложные задачи",
        description="Базовый сценарий для обучающего пособия ЕГЭ по математике с одной сложной тренировочной задачей.",
        defaults={
            "level": "ЕГЭ",
            "language": "русский",
            "content_source_mode": "materials_only",
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


def enforce_ai_rate_limit(request: Request) -> None:
    limit = settings.AI_RATE_LIMIT_PER_MINUTE
    if limit <= 0:
        return

    client = request.client.host if request.client else "unknown"
    key = f"{client}:{request.url.path}"
    now = time.monotonic()
    bucket = rate_limit_buckets[key]
    while bucket and now - bucket[0] >= 60:
        bucket.popleft()
    if len(bucket) >= limit:
        logger.warning(
            "ai rate limit exceeded client=%s path=%s limit=%s window_seconds=60",
            client,
            request.url.path,
            limit,
        )
        raise HTTPException(status_code=429, detail="AI rate limit exceeded. Try again later.")
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


def provider_error_detail(exc: AIGenerationError) -> str:
    if settings.DEBUG or settings.AI_EXPOSE_PROVIDER_ERRORS or exc.status_code < 500 or exc.status_code == 504:
        return str(exc)
    return "AI provider request failed. Check backend logs or provider configuration."


def text_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def text_preview(value: str) -> str:
    compact = " ".join(value.split())
    max_chars = settings.AI_LOG_PROMPT_PREVIEW_CHARS
    if max_chars <= 0:
        return ""
    if len(compact) <= max_chars:
        return compact
    return f"{compact[:max_chars]}..."


def build_generation_prompt_response(request: GenerationRequest) -> GenerationPromptResponse:
    enforce_text_limit("materials", request.materials, settings.AI_MAX_MATERIALS_CHARS)
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
        "ai prompt built provider=%s model=%s topic=%s materials_chars=%s prompt_chars=%s prompt_sha=%s warnings=%s prompt_preview=%s",
        request.provider or "default",
        request.model or "default",
        request.fields.topic or "-",
        len(request.materials),
        len(prompt),
        text_digest(prompt),
        len(warnings),
        text_preview(prompt),
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
    enforce_ai_rate_limit(request)
    logger.info(
        "ai prompt preview requested provider=%s model=%s topic=%s materials_chars=%s",
        generation_request.provider or "default",
        generation_request.model or "default",
        generation_request.fields.topic or "-",
        len(generation_request.materials),
    )
    return build_generation_prompt_response(generation_request)


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
async def generate_latex(request: Request, generation_request: GenerationRequest):
    enforce_ai_rate_limit(request)
    logger.info(
        "ai generation requested provider=%s model=%s topic=%s materials_chars=%s",
        generation_request.provider or "default",
        generation_request.model or "default",
        generation_request.fields.topic or "-",
        len(generation_request.materials),
    )
    prompt_response = build_generation_prompt_response(generation_request)
    started_at = time.perf_counter()

    try:
        raw_output, provider, model = await ai_generator.generate(
            prompt=prompt_response.prompt,
            provider=generation_request.provider,
            model=generation_request.model,
        )
    except AIGenerationError as exc:
        logger.warning(
            "ai generation failed provider=%s model=%s status_code=%s prompt_sha=%s duration_ms=%.2f error=%s",
            generation_request.provider or "default",
            generation_request.model or "default",
            exc.status_code,
            text_digest(prompt_response.prompt),
            (time.perf_counter() - started_at) * 1000,
            exc,
        )
        raise HTTPException(status_code=exc.status_code, detail=provider_error_detail(exc)) from exc

    enforce_text_limit("raw_output", raw_output, settings.AI_MAX_RAW_OUTPUT_CHARS)
    latex_body = extract_latex_code(raw_output)
    enforce_text_limit("latex_body", latex_body, settings.AI_MAX_RAW_OUTPUT_CHARS)
    latex_code = build_latex_document(latex_body)
    enforce_text_limit("latex_code", latex_code, settings.AI_MAX_RAW_OUTPUT_CHARS)
    validation = validate_latex_document(latex_code)
    logger.info(
        "ai generation completed provider=%s model=%s duration_ms=%.2f prompt_sha=%s raw_chars=%s body_chars=%s latex_chars=%s latex_sha=%s valid=%s errors=%s warnings=%s",
        provider,
        model,
        (time.perf_counter() - started_at) * 1000,
        text_digest(prompt_response.prompt),
        len(raw_output),
        len(latex_body),
        len(latex_code),
        text_digest(latex_code),
        validation["valid"],
        len(validation["errors"]),
        len(validation["warnings"]),
    )

    return GenerationResultResponse(
        status="success",
        prompt=prompt_response.prompt,
        warnings=prompt_response.warnings,
        provider=provider,
        model=model,
        latex_code=latex_code,
        raw_output=raw_output,
        validation=GenerationValidationResponse(**validation),
    )
