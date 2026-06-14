from collections import defaultdict, deque
import hashlib
import logging
import math
import shutil
import time

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.schemas import (
    GenerationPresetResponse,
    GenerationPromptResponse,
    GenerationProviderStatusResponse,
    GenerationRequest,
    GenerationHistoryResponse,
    GenerationCompileCheckResponse,
    GenerationResultResponse,
    GenerationTokenUsageResponse,
    GenerationValidationRequest,
    GenerationValidationResponse,
)
from app.config import settings
from app.database import get_db
from app.services.ai_generation import AIGenerationError, AIGenerationService, extract_latex_code
from app.services.latex_document_builder import build_latex_document
from app.services.latex_compiler import LatexCompiler
from app.services.latex_sanitizer import (
    sanitize_generated_latex_body,
    sanitize_generated_latex_body_for_safe_mode,
)
from app.services.latex_validator import validate_latex_document
from app.services.generation_history_service import GenerationHistoryNotFoundError, GenerationHistoryService
from app.services.prompt_builder import build_latex_generation_prompt, build_latex_repair_prompt
from app.services.token_counter import add_estimated_usage

logger = logging.getLogger(__name__)

router = APIRouter()

ai_generator = AIGenerationService()
generation_compiler = LatexCompiler()
generation_history_service = GenerationHistoryService()
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


def normalize_generated_body(content: str, *, safe_mode: bool) -> str:
    """Apply generation body normalization, including deterministic safe-mode simplification."""
    latex_body = sanitize_generated_latex_body(content)
    if safe_mode:
        latex_body = sanitize_generated_latex_body_for_safe_mode(latex_body)
    return latex_body


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



async def compile_check_and_repair(
    *,
    latex_body: str,
    raw_output: str,
    provider: str,
    model: str,
    safe_mode: bool,
    token_usage: GenerationTokenUsageResponse,
) -> tuple[str, str, str, dict[str, object], GenerationCompileCheckResponse]:
    """Compile-check generated LaTeX and ask the provider for one bounded repair when needed."""
    latex_body = normalize_generated_body(latex_body, safe_mode=safe_mode)
    latex_code = build_latex_document(latex_body)
    enforce_text_limit("latex_code", latex_code, settings.AI_MAX_RAW_OUTPUT_CHARS)
    validation = validate_latex_document(latex_code, safe_mode=safe_mode)

    compile_check = GenerationCompileCheckResponse()
    if not settings.AI_COMPILE_CHECK_ENABLED:
        compile_check.skipped_reason = "AI compile check is disabled."
        return latex_body, raw_output, latex_code, validation, compile_check

    if shutil.which(settings.LATEX_COMPILER) is None:
        compile_check.skipped_reason = f"LaTeX compiler '{settings.LATEX_COMPILER}' is not available."
        return latex_body, raw_output, latex_code, validation, compile_check

    max_attempts = max(settings.AI_REPAIR_ATTEMPTS, 0)
    compile_check.attempted = True

    for attempt in range(max_attempts + 1):
        compile_check.attempts = attempt + 1
        validation_errors = list(validation.get("errors") or [])
        if validation_errors:
            compile_error = "Validation failed before compile:\n" + "\n".join(validation_errors[:10])
            compile_check.error = compile_error
        else:
            compile_result = generation_compiler.compile(latex_code, {}, "main.tex")
            if compile_result.status == "success":
                compile_check.success = True
                compile_check.error = None
                return latex_body, raw_output, latex_code, validation, compile_check
            compile_error = compile_result.error or compile_result.output or "Compilation failed without details."
            compile_check.error = compile_error

        if attempt >= max_attempts:
            return latex_body, raw_output, latex_code, validation, compile_check

        repair_prompt = build_latex_repair_prompt(
            body=latex_body,
            compiler_error=compile_error,
            validation_errors=validation_errors,
        )
        enforce_text_limit("repair_prompt", repair_prompt, settings.AI_MAX_PROMPT_CHARS)
        logger.info(
            "ai generation repair requested provider=%s model=%s attempt=%s latex_sha=%s error_preview=%s",
            provider,
            model,
            attempt + 1,
            text_digest(latex_code),
            text_preview(compile_error),
        )
        repair_raw_output, _, _ = await ai_generator.generate(
            prompt=repair_prompt,
            provider=provider,
            model=model,
        )
        add_estimated_usage(token_usage, input_text=repair_prompt, output_text=repair_raw_output)
        enforce_text_limit("repair_raw_output", repair_raw_output, settings.AI_MAX_RAW_OUTPUT_CHARS)
        raw_output = repair_raw_output
        latex_body = normalize_generated_body(extract_latex_code(repair_raw_output), safe_mode=safe_mode)
        enforce_text_limit("repair_latex_body", latex_body, settings.AI_MAX_RAW_OUTPUT_CHARS)
        latex_code = build_latex_document(latex_body)
        enforce_text_limit("repair_latex_code", latex_code, settings.AI_MAX_RAW_OUTPUT_CHARS)
        validation = validate_latex_document(latex_code, safe_mode=safe_mode)
        compile_check.repaired = True

    return latex_body, raw_output, latex_code, validation, compile_check


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


def record_generation_failure(
    db: Session,
    *,
    generation_request: GenerationRequest,
    provider: str | None,
    model: str | None,
    prompt: str,
    error: str,
) -> None:
    generation_history_service.create_failure(
        db,
        project_id=generation_request.project_id,
        provider=provider or generation_request.provider or "default",
        model=model or generation_request.model,
        fields=generation_request.fields,
        prompt_hash=text_digest(prompt),
        prompt_preview=text_preview(prompt),
        error=error,
    )


def record_generation_success(
    db: Session,
    *,
    generation_request: GenerationRequest,
    provider: str,
    model: str,
    prompt: str,
    raw_output: str,
    latex_code: str,
    validation: dict[str, object],
    compile_check: GenerationCompileCheckResponse,
    token_usage: GenerationTokenUsageResponse,
) -> None:
    generation_history_service.create_success(
        db,
        project_id=generation_request.project_id,
        provider=provider,
        model=model,
        fields=generation_request.fields,
        prompt_hash=text_digest(prompt),
        prompt_preview=text_preview(prompt),
        raw_output_hash=text_digest(raw_output),
        latex_code_hash=text_digest(latex_code),
        latex_code_preview=text_preview(latex_code),
        validation=validation,
        compile_check=compile_check,
        token_usage=token_usage,
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
    enforce_ai_rate_limit(request)
    logger.info(
        "ai generation requested provider=%s model=%s topic=%s materials_chars=%s",
        generation_request.provider or "default",
        generation_request.model or "default",
        generation_request.fields.topic or "-",
        len(generation_request.materials),
    )
    prompt_response = build_generation_prompt_response(generation_request)
    token_usage = GenerationTokenUsageResponse()
    add_estimated_usage(token_usage, input_text=prompt_response.prompt)
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
        error_detail = provider_error_detail(exc)
        record_generation_failure(
            db,
            generation_request=generation_request,
            provider=generation_request.provider,
            model=generation_request.model,
            prompt=prompt_response.prompt,
            error=error_detail,
        )
        raise HTTPException(status_code=exc.status_code, detail=error_detail) from exc

    add_estimated_usage(token_usage, output_text=raw_output)
    enforce_text_limit("raw_output", raw_output, settings.AI_MAX_RAW_OUTPUT_CHARS)
    latex_body = sanitize_generated_latex_body(extract_latex_code(raw_output))
    enforce_text_limit("latex_body", latex_body, settings.AI_MAX_RAW_OUTPUT_CHARS)

    try:
        latex_body, raw_output, latex_code, validation, compile_check = await compile_check_and_repair(
            latex_body=latex_body,
            raw_output=raw_output,
            provider=provider,
            model=model,
            safe_mode=generation_request.fields.latex_mode == "safe",
            token_usage=token_usage,
        )
    except AIGenerationError as exc:
        logger.warning(
            "ai generation repair failed provider=%s model=%s status_code=%s prompt_sha=%s duration_ms=%.2f error=%s",
            provider,
            model,
            exc.status_code,
            text_digest(prompt_response.prompt),
            (time.perf_counter() - started_at) * 1000,
            exc,
        )
        error_detail = provider_error_detail(exc)
        record_generation_failure(
            db,
            generation_request=generation_request,
            provider=provider,
            model=model,
            prompt=prompt_response.prompt,
            error=error_detail,
        )
        raise HTTPException(status_code=exc.status_code, detail=error_detail) from exc

    logger.info(
        "ai generation completed provider=%s model=%s duration_ms=%.2f prompt_sha=%s raw_chars=%s body_chars=%s latex_chars=%s latex_sha=%s valid=%s errors=%s warnings=%s compile_attempted=%s compile_success=%s compile_repaired=%s input_tokens=%s output_tokens=%s total_tokens=%s token_source=%s",
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
        compile_check.attempted,
        compile_check.success,
        compile_check.repaired,
        token_usage.input_tokens,
        token_usage.output_tokens,
        token_usage.total_tokens,
        token_usage.source,
    )

    record_generation_success(
        db,
        generation_request=generation_request,
        provider=provider,
        model=model,
        prompt=prompt_response.prompt,
        raw_output=raw_output,
        latex_code=latex_code,
        validation=validation,
        compile_check=compile_check,
        token_usage=token_usage,
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
        compile_check=compile_check,
        token_usage=token_usage,
    )
