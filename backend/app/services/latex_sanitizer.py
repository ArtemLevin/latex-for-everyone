import re


ENUMITEM_PACKAGE_PATTERN = re.compile(
    r"\\usepackage\s*(?:\[(?P<options>[^\]]*)\])?\s*\{\s*enumitem\s*\}"
)
ENUMITEM_LIST_TRUE_OPTION_PATTERN = re.compile(r"^\s*list\s*=\s*true\s*$", re.IGNORECASE)
MICROTYPE_PACKAGE_PATTERN = re.compile(
    r"\\usepackage\s*(?:\[(?P<options>[^\]]*)\])?\s*\{\s*microtype\s*\}"
)
MICROTYPE_EXPANSION_OPTION_PATTERN = re.compile(r"^\s*expansion\s*=", re.IGNORECASE)
LATEX_FENCE_PATTERN = re.compile(r"```(?:latex|tex)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)
DOCUMENT_BODY_PATTERN = re.compile(r"\\begin\{document\}(?P<body>.*)\\end\{document\}", re.DOTALL)
BODY_PREAMBLE_LINE_PATTERN = re.compile(
    r"^\s*\\(?:documentclass|usepackage|geometry|definecolor|newcommand|renewcommand|newenvironment|usetikzlibrary|pgfplotsset)\b.*$",
    re.MULTILINE,
)
BODY_BOUNDARY_PATTERN = re.compile(r"\\(?:begin|end)\{document\}")
UNICODE_LATEX_REPLACEMENTS = {
    "≤": r"\le",
    "≥": r"\ge",
    "≠": r"\ne",
    "×": r"\times",
    "·": r"\cdot",
    "…": r"\ldots",
    "−": "-",
    "–": "--",
    "—": "---",
    "→": r"\to",
    "√": r"\sqrt{}",
    "π": r"\pi",
}
ENVIRONMENT_ALIASES = {
    "solution": (r"\textbf{Решение.}", ""),
    "example": (r"\begin{infoblock}{Пример}", r"\end{infoblock}"),
    "exercise": (r"\begin{taskblock}{Упражнение}", r"\end{taskblock}"),
    "problem": (r"\begin{taskblock}{Задача}", r"\end{taskblock}"),
    "proof": (r"\textbf{Доказательство.}", r"\hfill $\square$"),
}


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


def _strip_markdown_fence(content: str) -> str:
    match = LATEX_FENCE_PATTERN.search(content.strip())
    return match.group(1).strip() if match else content


def _extract_body_if_full_document(content: str) -> str:
    match = DOCUMENT_BODY_PATTERN.search(content)
    return match.group("body").strip() if match else content


def _replace_unicode_symbols(content: str) -> str:
    sanitized = content
    for symbol, replacement in UNICODE_LATEX_REPLACEMENTS.items():
        sanitized = sanitized.replace(symbol, replacement)
    return sanitized


def _replace_environment_aliases(content: str) -> str:
    sanitized = content
    for name, (begin_replacement, end_replacement) in ENVIRONMENT_ALIASES.items():
        sanitized = re.sub(
            rf"\\begin\{{{re.escape(name)}\}}(?:\{{([^}}]*)\}})?",
            lambda _match, replacement=begin_replacement: replacement,
            sanitized,
        )
        sanitized = re.sub(
            rf"\\end\{{{re.escape(name)}\}}",
            lambda _match, replacement=end_replacement: replacement,
            sanitized,
        )
    return sanitized


def sanitize_latex_source(content: str) -> str:
    """Normalize known AI-generated LaTeX package mistakes before compilation."""
    sanitized = ENUMITEM_PACKAGE_PATTERN.sub(_sanitize_enumitem_package, content)
    return MICROTYPE_PACKAGE_PATTERN.sub(_sanitize_microtype_package, sanitized)


def sanitize_generated_latex_body(content: str) -> str:
    """Normalize common model mistakes before wrapping a body in the fixed preamble."""
    sanitized = _strip_markdown_fence(content)
    sanitized = _extract_body_if_full_document(sanitized)
    sanitized = BODY_PREAMBLE_LINE_PATTERN.sub("", sanitized)
    sanitized = BODY_BOUNDARY_PATTERN.sub("", sanitized)
    sanitized = _replace_environment_aliases(sanitized)
    sanitized = _replace_unicode_symbols(sanitized)
    sanitized = sanitize_latex_source(sanitized)
    return re.sub(r"\n{3,}", "\n\n", sanitized).strip()


def sanitize_latex_files(files: dict[str, str]) -> dict[str, str]:
    """Return a sanitized copy of a project file map."""
    return {filename: sanitize_latex_source(content) for filename, content in files.items()}
