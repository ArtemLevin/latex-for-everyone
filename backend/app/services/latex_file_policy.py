from collections.abc import Iterable, Mapping
from pathlib import PurePosixPath


DEFAULT_ALLOWED_LATEX_EXTENSIONS = frozenset({".tex", ".bib", ".cls", ".sty"})


class LatexFilePolicyError(ValueError):
    """Raised when a LaTeX project filename is unsafe or unsupported."""


def parse_allowed_extensions(value: str | Iterable[str] | None) -> frozenset[str]:
    """Normalize configured extension allowlists to lowercase dot-prefixed suffixes."""
    if value is None:
        return DEFAULT_ALLOWED_LATEX_EXTENSIONS
    if isinstance(value, str):
        raw_items = [item.strip() for item in value.split(",")]
    else:
        raw_items = [str(item).strip() for item in value]

    normalized = []
    for item in raw_items:
        if not item:
            continue
        normalized.append(item.lower() if item.startswith(".") else f".{item.lower()}")
    return frozenset(normalized) or DEFAULT_ALLOWED_LATEX_EXTENSIONS


def validate_latex_filename(
    filename: str,
    *,
    allowed_extensions: Iterable[str] | None = None,
) -> str:
    """Return a normalized safe relative filename or raise for traversal/unsupported suffixes."""
    if not filename or filename.startswith(("/", "\\")) or "\\" in filename:
        raise LatexFilePolicyError(f"Invalid LaTeX filename: {filename}")

    path = PurePosixPath(filename)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise LatexFilePolicyError(f"Invalid LaTeX filename: {filename}")

    suffix = path.suffix.lower()
    allowed = frozenset(allowed_extensions or DEFAULT_ALLOWED_LATEX_EXTENSIONS)
    if suffix not in allowed:
        allowed_text = ", ".join(sorted(allowed))
        raise LatexFilePolicyError(f"Unsupported LaTeX file extension for '{filename}'. Allowed extensions: {allowed_text}")

    return path.as_posix()


def enforce_latex_file_policy(
    files: Mapping[str, str],
    *,
    allowed_extensions: Iterable[str] | None = None,
) -> dict[str, str]:
    """Validate and normalize file names before filesystem/archive/compiler boundaries."""
    normalized: dict[str, str] = {}
    for filename, content in files.items():
        safe_name = validate_latex_filename(filename, allowed_extensions=allowed_extensions)
        normalized[safe_name] = content
    return normalized
