import re


ENUMITEM_PACKAGE_PATTERN = re.compile(
    r"\\usepackage\s*(?:\[(?P<options>[^\]]*)\])?\s*\{\s*enumitem\s*\}"
)
ENUMITEM_LIST_TRUE_OPTION_PATTERN = re.compile(r"^\s*list\s*=\s*true\s*$", re.IGNORECASE)
MICROTYPE_PACKAGE_PATTERN = re.compile(
    r"\\usepackage\s*(?:\[(?P<options>[^\]]*)\])?\s*\{\s*microtype\s*\}"
)
MICROTYPE_EXPANSION_OPTION_PATTERN = re.compile(r"^\s*expansion\s*=", re.IGNORECASE)


def _split_latex_options(options: str | None) -> list[str]:
    if options is None:
        return []
    return [option.strip() for option in options.split(",") if option.strip()]


def _sanitize_enumitem_package(match: re.Match[str]) -> str:
    options = match.group("options")
    if options is None:
        return match.group(0)

    original_options = _split_latex_options(options)
    kept_options = [
        option
        for option in original_options
        if not ENUMITEM_LIST_TRUE_OPTION_PATTERN.fullmatch(option)
    ]
    if len(kept_options) == len(original_options):
        return match.group(0)
    if kept_options:
        return rf"\usepackage[{','.join(kept_options)}]{{enumitem}}"
    return r"\usepackage{enumitem}"


def _sanitize_microtype_package(match: re.Match[str]) -> str:
    """Disable expansion because pdfTeX cannot expand bitmap T2A fonts reliably."""
    options = match.group("options")
    original_options = _split_latex_options(options)
    kept_options = [
        option
        for option in original_options
        if not MICROTYPE_EXPANSION_OPTION_PATTERN.match(option)
    ]
    kept_options.append("expansion=false")

    if options is not None and kept_options == original_options:
        return match.group(0)
    return rf"\usepackage[{','.join(kept_options)}]{{microtype}}"


def sanitize_latex_source(content: str) -> str:
    """Normalize known AI-generated LaTeX package mistakes before compilation."""
    sanitized = ENUMITEM_PACKAGE_PATTERN.sub(_sanitize_enumitem_package, content)
    return MICROTYPE_PACKAGE_PATTERN.sub(_sanitize_microtype_package, sanitized)


def sanitize_latex_files(files: dict[str, str]) -> dict[str, str]:
    """Return a sanitized copy of a project file map."""
    return {filename: sanitize_latex_source(content) for filename, content in files.items()}
