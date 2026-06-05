import re


ENUMITEM_PACKAGE_PATTERN = re.compile(
    r"\\usepackage\s*(?:\[(?P<options>[^\]]*)\])?\s*\{\s*enumitem\s*\}"
)
ENUMITEM_LIST_TRUE_OPTION_PATTERN = re.compile(r"^\s*list\s*=\s*true\s*$", re.IGNORECASE)


def _sanitize_enumitem_package(match: re.Match[str]) -> str:
    options = match.group("options")
    if options is None:
        return match.group(0)

    kept_options = [
        option.strip()
        for option in options.split(",")
        if option.strip() and not ENUMITEM_LIST_TRUE_OPTION_PATTERN.fullmatch(option)
    ]
    if len(kept_options) == len([option for option in options.split(",") if option.strip()]):
        return match.group(0)
    if kept_options:
        return rf"\usepackage[{','.join(kept_options)}]{{enumitem}}"
    return r"\usepackage{enumitem}"


def sanitize_latex_source(content: str) -> str:
    """Normalize known AI-generated LaTeX package mistakes before compilation."""
    return ENUMITEM_PACKAGE_PATTERN.sub(_sanitize_enumitem_package, content)


def sanitize_latex_files(files: dict[str, str]) -> dict[str, str]:
    """Return a sanitized copy of a project file map."""
    return {filename: sanitize_latex_source(content) for filename, content in files.items()}
