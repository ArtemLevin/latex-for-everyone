import hashlib
import logging
import shutil
import time

from sqlalchemy.orm import Session

from app.config import settings
from app.schemas import (
    GenerationCompileCheckResponse,
    GenerationPromptResponse,
    GenerationRequest,
    GenerationResultResponse,
    GenerationTokenUsageResponse,
    GenerationValidationResponse,
)
from app.services.ai_generation import AIGenerationError, AIGenerationService, extract_latex_code
from app.services.generation_history_service import GenerationHistoryService
from app.services.latex_compiler import LatexCompiler
from app.services.latex_document_builder import build_latex_document
from app.services.latex_sanitizer import sanitize_generated_latex_body, sanitize_generated_latex_body_for_safe_mode
from app.services.latex_validator import validate_latex_document
from app.services.prompt_builder import build_latex_repair_prompt
from app.services.token_counter import add_estimated_usage

logger = logging.getLogger(__name__)


class GenerationOrchestrationError(Exception):
    """Raised when the generation service needs the router to return a specific HTTP error."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


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


def provider_error_detail(exc: AIGenerationError) -> str:
    if settings.DEBUG or settings.AI_EXPOSE_PROVIDER_ERRORS or exc.status_code < 500 or exc.status_code == 504:
        return str(exc)
    return "AI provider request failed. Check backend logs or provider configuration."


class GenerationOrchestrator:
    """Coordinates provider calls, repair, validation, and history for AI generation."""

    def __init__(
        self,
        *,
        ai_generator: AIGenerationService,
        compiler: LatexCompiler,
        history_service: GenerationHistoryService,
    ):
        self.ai_generator = ai_generator
        self.compiler = compiler
        self.history_service = history_service

    def _enforce_text_limit(self, label: str, value: str, max_chars: int) -> None:
        if max_chars > 0 and len(value) > max_chars:
            logger.warning(
                "ai text limit exceeded label=%s length=%s max_chars=%s",
                label,
                len(value),
                max_chars,
            )
            raise GenerationOrchestrationError(413, f"{label} exceeds {max_chars} characters.")

    def _normalize_generated_body(self, content: str, *, safe_mode: bool) -> str:
        latex_body = sanitize_generated_latex_body(content)
        if safe_mode:
            latex_body = sanitize_generated_latex_body_for_safe_mode(latex_body)
        return latex_body

    def _record_generation_failure(
        self,
        db: Session,
        *,
        generation_request: GenerationRequest,
        owner_id: str,
        provider: str | None,
        model: str | None,
        prompt: str,
        error: str,
    ) -> None:
        self.history_service.create_failure(
            db,
            project_id=generation_request.project_id,
            owner_id=owner_id,
            provider=provider or generation_request.provider or "default",
            model=model or generation_request.model,
            fields=generation_request.fields,
            prompt_hash=text_digest(prompt),
            prompt_preview=text_preview(prompt),
            error=error,
        )

    def _record_generation_success(
        self,
        db: Session,
        *,
        generation_request: GenerationRequest,
        owner_id: str,
        provider: str,
        model: str,
        prompt: str,
        raw_output: str,
        latex_code: str,
        validation: dict[str, object],
        compile_check: GenerationCompileCheckResponse,
        token_usage: GenerationTokenUsageResponse,
    ) -> None:
        self.history_service.create_success(
            db,
            project_id=generation_request.project_id,
            owner_id=owner_id,
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

    async def _compile_check_and_repair(
        self,
        *,
        latex_body: str,
        raw_output: str,
        provider: str,
        model: str,
        safe_mode: bool,
        token_usage: GenerationTokenUsageResponse,
    ) -> tuple[str, str, str, dict[str, object], GenerationCompileCheckResponse]:
        latex_body = self._normalize_generated_body(latex_body, safe_mode=safe_mode)
        latex_code = build_latex_document(latex_body)
        self._enforce_text_limit("latex_code", latex_code, settings.AI_MAX_RAW_OUTPUT_CHARS)
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
                compile_result = self.compiler.compile(latex_code, {}, "main.tex")
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
            self._enforce_text_limit("repair_prompt", repair_prompt, settings.AI_MAX_PROMPT_CHARS)
            logger.info(
                "ai generation repair requested provider=%s model=%s attempt=%s latex_sha=%s error_preview=%s",
                provider,
                model,
                attempt + 1,
                text_digest(latex_code),
                text_preview(compile_error),
            )
            repair_raw_output, _, _ = await self.ai_generator.generate(
                prompt=repair_prompt,
                provider=provider,
                model=model,
            )
            add_estimated_usage(token_usage, input_text=repair_prompt, output_text=repair_raw_output)
            self._enforce_text_limit("repair_raw_output", repair_raw_output, settings.AI_MAX_RAW_OUTPUT_CHARS)
            raw_output = repair_raw_output
            latex_body = self._normalize_generated_body(extract_latex_code(repair_raw_output), safe_mode=safe_mode)
            self._enforce_text_limit("repair_latex_body", latex_body, settings.AI_MAX_RAW_OUTPUT_CHARS)
            latex_code = build_latex_document(latex_body)
            self._enforce_text_limit("repair_latex_code", latex_code, settings.AI_MAX_RAW_OUTPUT_CHARS)
            validation = validate_latex_document(latex_code, safe_mode=safe_mode)
            compile_check.repaired = True

        return latex_body, raw_output, latex_code, validation, compile_check

    async def generate(
        self,
        *,
        db: Session,
        generation_request: GenerationRequest,
        prompt_response: GenerationPromptResponse,
        request_sha: str,
        owner_id: str,
    ) -> GenerationResultResponse:
        token_usage = GenerationTokenUsageResponse()
        add_estimated_usage(token_usage, input_text=prompt_response.prompt)
        started_at = time.perf_counter()

        try:
            raw_output, provider, model = await self.ai_generator.generate(
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
            self._record_generation_failure(
                db,
                generation_request=generation_request,
                owner_id=owner_id,
                provider=generation_request.provider,
                model=generation_request.model,
                prompt=prompt_response.prompt,
                error=error_detail,
            )
            raise GenerationOrchestrationError(exc.status_code, error_detail) from exc

        add_estimated_usage(token_usage, output_text=raw_output)
        self._enforce_text_limit("raw_output", raw_output, settings.AI_MAX_RAW_OUTPUT_CHARS)
        latex_body = sanitize_generated_latex_body(extract_latex_code(raw_output))
        self._enforce_text_limit("latex_body", latex_body, settings.AI_MAX_RAW_OUTPUT_CHARS)

        try:
            latex_body, raw_output, latex_code, validation, compile_check = await self._compile_check_and_repair(
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
            self._record_generation_failure(
                db,
                generation_request=generation_request,
                owner_id=owner_id,
                provider=provider,
                model=model,
                prompt=prompt_response.prompt,
                error=error_detail,
            )
            raise GenerationOrchestrationError(exc.status_code, error_detail) from exc

        logger.info(
            "ai generation completed provider=%s model=%s duration_ms=%.2f prompt_sha=%s request_sha=%s raw_chars=%s body_chars=%s latex_chars=%s latex_sha=%s valid=%s errors=%s warnings=%s compile_attempted=%s compile_success=%s compile_repaired=%s input_tokens=%s output_tokens=%s total_tokens=%s token_source=%s",
            provider,
            model,
            (time.perf_counter() - started_at) * 1000,
            text_digest(prompt_response.prompt),
            request_sha,
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

        self._record_generation_success(
            db,
            generation_request=generation_request,
            owner_id=owner_id,
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
