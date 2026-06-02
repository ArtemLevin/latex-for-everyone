import re
from typing import Any

import httpx

from app.config import settings


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

    async def generate(self, prompt: str, provider: str | None = None, model: str | None = None) -> tuple[str, str, str]:
        resolved_provider = (provider or settings.AI_PROVIDER).strip().lower()

        if resolved_provider == "ollama":
            resolved_model = model or settings.OLLAMA_MODEL
            output = await self._generate_ollama(prompt, resolved_model)
        elif resolved_provider in {"openai", "vendor", "openai_compatible"}:
            resolved_provider = "openai_compatible"
            resolved_model = model or settings.AI_VENDOR_MODEL
            output = await self._generate_openai_compatible(prompt, resolved_model)
        else:
            raise AIGenerationError(f"Unsupported AI provider: {provider}", status_code=400)

        return output, resolved_provider, resolved_model

    async def _generate_ollama(self, prompt: str, model: str) -> str:
        url = f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/generate"
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": False,
        }
        try:
            async with httpx.AsyncClient(timeout=settings.AI_GENERATION_TIMEOUT) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AIGenerationError(f"Ollama generation failed: {exc}") from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise AIGenerationError("Ollama returned invalid JSON") from exc

        generated = data.get("response")
        if not isinstance(generated, str) or not generated.strip():
            raise AIGenerationError("Ollama returned an empty generation response")
        return generated

    async def _generate_openai_compatible(self, prompt: str, model: str) -> str:
        if not settings.AI_VENDOR_API_KEY:
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

        try:
            async with httpx.AsyncClient(timeout=settings.AI_GENERATION_TIMEOUT) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
        except httpx.HTTPError as exc:
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
            raise AIGenerationError("Vendor returned an empty generation response")
        return generated
