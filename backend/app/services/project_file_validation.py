from collections.abc import Mapping

from app.config import settings
from app.services.latex_file_policy import enforce_latex_file_policy, parse_allowed_extensions
from app.services.payload_limits import enforce_latex_payload_limits


def validate_project_latex_files(files: Mapping[str, str]) -> dict[str, str]:
    """Validate filenames and LaTeX text-size limits for a future project file map."""
    normalized = enforce_latex_file_policy(
        files,
        allowed_extensions=parse_allowed_extensions(settings.LATEX_ALLOWED_EXTENSIONS),
    )
    enforce_latex_payload_limits(
        normalized,
        max_files=settings.MAX_LATEX_FILES,
        max_file_chars=settings.MAX_LATEX_FILE_CHARS,
        max_total_chars=settings.MAX_LATEX_TOTAL_CHARS,
    )
    return normalized
