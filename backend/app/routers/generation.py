from collections import defaultdict, deque
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
from app.services.prompt_builder import build_latex_generation_prompt
from app.services.latex_validator import validate_latex_document

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
        raise HTTPException(status_code=429, detail="AI rate limit exceeded. Try again later.")
    bucket.append(now)


def enforce_text_limit(label: str, value: str, max_chars: int) -> None:
    if max_chars > 0 and len(value) > max_chars:
        raise HTTPException(
            status_code=413,
            detail=f"{label} exceeds {max_chars} characters.",
        )


def provider_error_detail(exc: AIGenerationError) -> str:
    if settings.DEBUG or settings.AI_EXPOSE_PROVIDER_ERRORS or exc.status_code < 500:
        return str(exc)
    return "AI provider request failed. Check backend logs or provider configuration."


def build_generation_prompt_response(request: GenerationRequest) -> GenerationPromptResponse:
    enforce_text_limit("materials", request.materials, settings.AI_MAX_MATERIALS_CHARS)
    prompt = build_latex_generation_prompt(request.fields, request.materials)
    enforce_text_limit("prompt", prompt, settings.AI_MAX_PROMPT_CHARS)
    warnings = []
    if not request.fields.topic:
        warnings.append("Тема не указана: prompt потребует определить тему по материалам без домыслов.")
    if not request.materials.strip():
        warnings.append("Материалы не переданы: prompt запрещает домысливать исходные задания.")

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
    return build_generation_prompt_response(generation_request)


@router.get("/providers/status", response_model=GenerationProviderStatusResponse)
async def get_generation_provider_status(
    request: Request,
    provider: str | None = Query(default=None),
    model: str | None = Query(default=None),
):
    enforce_ai_rate_limit(request)
    try:
        status = await ai_generator.get_provider_status(provider=provider, model=model)
    except AIGenerationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=provider_error_detail(exc)) from exc
    return GenerationProviderStatusResponse(**status)


@router.post("/validate", response_model=GenerationValidationResponse)
async def validate_generated_latex(request: Request, validation_request: GenerationValidationRequest):
    enforce_ai_rate_limit(request)
    enforce_text_limit("latex_code", validation_request.latex_code, settings.AI_MAX_RAW_OUTPUT_CHARS)
    return GenerationValidationResponse(**validate_latex_document(validation_request.latex_code))


@router.post("/generate", response_model=GenerationResultResponse)
async def generate_latex(request: Request, generation_request: GenerationRequest):
    enforce_ai_rate_limit(request)
    prompt_response = build_generation_prompt_response(generation_request)

    try:
        raw_output, provider, model = await ai_generator.generate(
            prompt=prompt_response.prompt,
            provider=generation_request.provider,
            model=generation_request.model,
        )
    except AIGenerationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=provider_error_detail(exc)) from exc

    enforce_text_limit("raw_output", raw_output, settings.AI_MAX_RAW_OUTPUT_CHARS)
    latex_code = extract_latex_code(raw_output)
    enforce_text_limit("latex_code", latex_code, settings.AI_MAX_RAW_OUTPUT_CHARS)
    validation = validate_latex_document(latex_code)

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
