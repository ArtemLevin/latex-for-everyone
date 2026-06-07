import re

from app.schemas import GenerationTokenUsageResponse

TOKEN_PATTERN = re.compile(r"\w+|[^\s\w]", re.UNICODE)


def estimate_token_count(text: str) -> int:
    """Return a deterministic tokenizer-free estimate for generation accounting."""
    if not text:
        return 0
    return len(TOKEN_PATTERN.findall(text))


def add_estimated_usage(
    usage: GenerationTokenUsageResponse,
    *,
    input_text: str = "",
    output_text: str = "",
) -> GenerationTokenUsageResponse:
    """Accumulate estimated input/output tokens and refresh the total."""
    usage.input_tokens += estimate_token_count(input_text)
    usage.output_tokens += estimate_token_count(output_text)
    usage.total_tokens = usage.input_tokens + usage.output_tokens
    return usage
