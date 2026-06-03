import logging
import re
import time
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class AIGenerationError(Exception):
    """Raised when a generation provider cannot return a usable response."""

    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


LATEX_FENCE_PATTERN = re.compile(r"```(?:latex|tex)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)


def extract_latex_code(text: str) -> str:
    """Extract LaTeX from a fenced model response or return the trimmed output."""
    stripped = text.strip()
    match = LATEX_FENCE_PATTERN.search(stripped)
    if match:
        return match.group(1).strip()

    document_start = stripped.find(r"\documentclass")
    document_end = stripped.rfind(r"\end{document}")
    if document_start != -1 and document_end != -1:
        document_end += len(r"\end{document}")
        return stripped[document_start:document_end].strip()

    return stripped


class AIGenerationService:
    """Provider adapter for AI-backed LaTeX generation."""

    def resolve_provider_model(self, provider: str | None = None, model: str | None = None) -> tuple[str, str]:
        requested_provider = provider or settings.AI_PROVIDER
        resolved_provider = requested_provider.strip().lower()
        if resolved_provider == "ollama":
            resolved = ("ollama", model or settings.OLLAMA_MODEL)
        elif resolved_provider in {"openai", "vendor", "openai_compatible"}:
            resolved = ("openai_compatible", model or settings.AI_VENDOR_MODEL)
        else:
            logger.warning("ai provider unsupported provider=%s", provider)
            raise AIGenerationError(f"Unsupported AI provider: {provider}", status_code=400)
        logger.debug(
            "ai provider resolved requested_provider=%s requested_model=%s provider=%s model=%s",
            requested_provider,
            model or "default",
            resolved[0],
            resolved[1],
        )
        return resolved

    async def get_provider_status(self, provider: str | None = None, model: str | None = None) -> dict[str, object]:
        resolved_provider, resolved_model = self.resolve_provider_model(provider, model)
        logger.info("ai provider status start provider=%s model=%s", resolved_provider, resolved_model)
        started_at = time.perf_counter()
        if resolved_provider == "ollama":
            status = await self._get_ollama_status(resolved_model)
        else:
            status = await self._get_openai_compatible_status(resolved_model)
        logger.info(
            "ai provider status result provider=%s model=%s available=%s model_available=%s duration_ms=%.2f",
            resolved_provider,
            resolved_model,
            status.get("available"),
            status.get("model_available"),
            (time.perf_counter() - started_at) * 1000,
        )
        return status

    async def generate(self, prompt: str, provider: str | None = None, model: str | None = None) -> tuple[str, str, str]:
        resolved_provider, resolved_model = self.resolve_provider_model(provider, model)
        logger.info(
            "ai generation provider call start provider=%s model=%s prompt_chars=%s",
            resolved_provider,
            resolved_model,
            len(prompt),
        )
        started_at = time.perf_counter()

        if resolved_provider == "ollama":
            output = await self._generate_ollama(prompt, resolved_model)
        else:
            output = await self._generate_openai_compatible(prompt, resolved_model)

        logger.info(
            "ai generation provider call completed provider=%s model=%s output_chars=%s duration_ms=%.2f",
            resolved_provider,
            resolved_model,
            len(output),
            (time.perf_counter() - started_at) * 1000,
        )
        return output, resolved_provider, resolved_model

    async def _get_ollama_status(self, model: str) -> dict[str, object]:
        url = f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/tags"
        try:
            async with httpx.AsyncClient(timeout=settings.AI_PROVIDER_STATUS_TIMEOUT) as client:
                response = await client.get(url)
                response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("ollama status unavailable model=%s url=%s error=%s", model, url, exc)
            return {
                "provider": "ollama",
                "model": model,
                "available": False,
                "message": f"Ollama unavailable: {exc}",
                "models": [],
                "model_available": False,
            }

        models = [item.get("name", "") for item in data.get("models", []) if item.get("name")]
        model_available = any(name == model or name.startswith(f"{model}:") for name in models)
        return {
            "provider": "ollama",
            "model": model,
            "available": True,
            "message": "Ollama is reachable." if model_available else "Ollama is reachable, but the requested model was not found.",
            "models": models,
            "model_available": model_available,
        }

    async def _get_openai_compatible_status(self, model: str) -> dict[str, object]:
        if not settings.AI_VENDOR_API_KEY:
            logger.warning("vendor status skipped model=%s reason=missing_api_key", model)
            return {
                "provider": "openai_compatible",
                "model": model,
                "available": False,
                "message": "AI_VENDOR_API_KEY is not configured.",
                "models": [],
                "model_available": None,
            }

        url = f"{settings.AI_VENDOR_BASE_URL.rstrip('/')}/models"
        headers = {"Authorization": f"Bearer {settings.AI_VENDOR_API_KEY}"}
        try:
            async with httpx.AsyncClient(timeout=settings.AI_PROVIDER_STATUS_TIMEOUT) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("vendor status unavailable model=%s base_url=%s error=%s", model, settings.AI_VENDOR_BASE_URL, exc)
            return {
                "provider": "openai_compatible",
                "model": model,
                "available": False,
                "message": f"Vendor unavailable: {exc}",
                "models": [],
                "model_available": None,
            }

        models = [item.get("id", "") for item in data.get("data", []) if item.get("id")]
        model_available = model in models if models else None
        return {
            "provider": "openai_compatible",
            "model": model,
            "available": True,
            "message": "Vendor is reachable." if model_available is not False else "Vendor is reachable, but the requested model was not listed.",
            "models": models,
            "model_available": model_available,
        }

    async def _generate_ollama(self, prompt: str, model: str) -> str:
        url = f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/generate"
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": False,
        }
        logger.info("ollama generation request model=%s url=%s prompt_chars=%s", model, url, len(prompt))
        try:
            async with httpx.AsyncClient(timeout=settings.AI_GENERATION_TIMEOUT) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            logger.warning(
                "ollama generation timeout model=%s url=%s timeout_seconds=%s",
                model,
                url,
                settings.AI_GENERATION_TIMEOUT,
            )
            raise AIGenerationError(
                f"Ollama generation timed out after {settings.AI_GENERATION_TIMEOUT} seconds. "
                "Check that Ollama is running, the model is pulled and loaded, or increase AI_GENERATION_TIMEOUT.",
                status_code=504,
            ) from exc
        except httpx.HTTPError as exc:
            logger.warning("ollama generation http error model=%s url=%s error=%s", model, url, exc)
            raise AIGenerationError(f"Ollama generation failed: {exc}") from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise AIGenerationError("Ollama returned invalid JSON") from exc

        generated = data.get("response")
        if not isinstance(generated, str) or not generated.strip():
            logger.warning("ollama generation empty response model=%s", model)
            raise AIGenerationError("Ollama returned an empty generation response")
        logger.info("ollama generation response model=%s output_chars=%s", model, len(generated))
        return generated

    async def _generate_openai_compatible(self, prompt: str, model: str) -> str:
        if not settings.AI_VENDOR_API_KEY:
            logger.warning("vendor generation rejected model=%s reason=missing_api_key", model)
            raise AIGenerationError("AI_VENDOR_API_KEY is required for vendor generation", status_code=400)

        url = f"{settings.AI_VENDOR_BASE_URL.rstrip('/')}/chat/completions"
        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": "Return only the requested compilable LaTeX document."},
                {"role": "user", "content": prompt},
            ],
            "temperature": settings.AI_VENDOR_TEMPERATURE,
        }
        headers = {
            "Authorization": f"Bearer {settings.AI_VENDOR_API_KEY}",
            "Content-Type": "application/json",
        }

        logger.info("vendor generation request model=%s base_url=%s prompt_chars=%s", model, settings.AI_VENDOR_BASE_URL, len(prompt))
        try:
            async with httpx.AsyncClient(timeout=settings.AI_GENERATION_TIMEOUT) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            logger.warning(
                "vendor generation timeout model=%s base_url=%s timeout_seconds=%s",
                model,
                settings.AI_VENDOR_BASE_URL,
                settings.AI_GENERATION_TIMEOUT,
            )
            raise AIGenerationError(
                f"Vendor generation timed out after {settings.AI_GENERATION_TIMEOUT} seconds. "
                "Check provider availability or increase AI_GENERATION_TIMEOUT.",
                status_code=504,
            ) from exc
        except httpx.HTTPError as exc:
            logger.warning("vendor generation http error model=%s base_url=%s error=%s", model, settings.AI_VENDOR_BASE_URL, exc)
            raise AIGenerationError(f"Vendor generation failed: {exc}") from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise AIGenerationError("Vendor returned invalid JSON") from exc

        try:
            generated = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AIGenerationError("Vendor returned an unexpected generation response") from exc

        if not isinstance(generated, str) or not generated.strip():
            logger.warning("vendor generation empty response model=%s", model)
            raise AIGenerationError("Vendor returned an empty generation response")
        logger.info("vendor generation response model=%s output_chars=%s", model, len(generated))
        return generated
