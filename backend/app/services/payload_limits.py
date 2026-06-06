from collections.abc import Mapping


class PayloadLimitError(ValueError):
    """Raised when a user-provided LaTeX file payload exceeds safety limits."""


def enforce_latex_payload_limits(
    files: Mapping[str, str],
    *,
    max_files: int,
    max_file_chars: int,
    max_total_chars: int,
) -> None:
    """Validate file-count and text-size limits before compile/export boundaries."""
    if max_files > 0 and len(files) > max_files:
        raise PayloadLimitError(f"Too many LaTeX files: {len(files)} exceeds limit {max_files}")

    total_chars = 0
    for filename, content in files.items():
        content_chars = len(content or "")
        if max_file_chars > 0 and content_chars > max_file_chars:
            raise PayloadLimitError(
                f"LaTeX file '{filename}' is too large: {content_chars} chars exceeds limit {max_file_chars}"
            )
        total_chars += content_chars

    if max_total_chars > 0 and total_chars > max_total_chars:
        raise PayloadLimitError(f"LaTeX payload is too large: {total_chars} chars exceeds limit {max_total_chars}")
