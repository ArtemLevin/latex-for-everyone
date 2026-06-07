import re


FORBIDDEN_LATEX_PATTERNS = {
    r"\\uppercase\b": "Запрещена команда \\uppercase.",
    r"\\write18\b": "Запрещена команда \\write18.",
    r"\\openout(?:\b|\d)": "Запрещена команда \\openout.",
    r"\\input\s*\|": "Запрещен shell-pipe ввод через \\input|... .",
    r"\\(?:input|include)\s*\{\s*(?:/|\.\.|[A-Za-z]:)": "Запрещены абсолютные и родительские пути в \\input/\\include.",
    r"\\includegraphics(?:\[[^\]]*\])?\s*\{\s*(?:/|\.\.|[A-Za-z]:|https?://)": "Запрещены внешние, абсолютные и родительские пути в \\includegraphics.",
    r"\\usepackage\s*\[[^\]]*\blist\s*=\s*true\b[^\]]*\]\s*\{\s*enumitem\s*\}": "Опция list=true недопустима для enumitem; используйте \\usepackage{enumitem} без этой опции.",
}

BODY_FORBIDDEN_LATEX_PATTERNS = {
    r"\\documentclass\b": "Тело документа не должно содержать \\documentclass; backend добавляет преамбулу автоматически.",
    r"\\usepackage\b": "Тело документа не должно содержать \\usepackage; используйте только пакеты фиксированной преамбулы.",
    r"\\(?:newcommand|renewcommand|newenvironment|renewenvironment)\b": "Тело документа не должно объявлять новые команды или окружения.",
    r"\\(?:geometry|definecolor|usetikzlibrary|pgfplotsset)\b": "Тело документа не должно менять преамбулу, geometry, colors или библиотеки.",
}

SAFE_MODE_FORBIDDEN_BODY_PATTERNS = {
    r"\\begin\{tikzpicture\}": "Safe LaTeX mode forbids tikzpicture; замените рисунок текстовым объяснением или простой формулой.",
    r"\\begin\{axis\}": "Safe LaTeX mode forbids pgfplots axis; замените график текстовым объяснением или таблицей.",
    r"\\addplot\b": "Safe LaTeX mode forbids pgfplots \\addplot; замените график текстовым объяснением.",
    r"\\begin\{longtable\}": "Safe LaTeX mode forbids longtable; используйте простой tabularx или список.",
    r"\\includegraphics\b": "Safe LaTeX mode forbids \\includegraphics; внешние изображения не поддерживаются в AI-body.",
}

REQUIRED_LATEX_PACKAGES = [
    "fontenc",
    "inputenc",
    "babel",
    "amsmath",
    "amssymb",
    "mathtools",
    "geometry",
    "hyperref",
    "tabularx",
]

BALANCED_ENVIRONMENTS = [
    "document",
    "infoblock",
    "taskblock",
    "enumerate",
    "itemize",
    "center",
    "tabularx",
    "longtable",
    "tikzpicture",
    "equation",
    "equation*",
    "align",
    "align*",
]

DOCUMENT_BODY_RE = re.compile(r"\\begin\{document\}(?P<body>.*)\\end\{document\}", re.DOTALL)


def _extract_document_body(content: str) -> str:
    match = DOCUMENT_BODY_RE.search(content)
    return match.group("body") if match else content


def _append_environment_balance_errors(content: str, errors: list[str]) -> None:
    for env in BALANCED_ENVIRONMENTS:
        begins = len(re.findall(rf"\\begin\{{{re.escape(env)}\}}", content))
        ends = len(re.findall(rf"\\end\{{{re.escape(env)}\}}", content))
        if begins != ends:
            errors.append(f"Несбалансированное окружение {env}: begin={begins}, end={ends}.")


def _append_math_delimiter_errors(content: str, errors: list[str]) -> None:
    if len(re.findall(r"(?<!\\)\$", content)) % 2:
        errors.append("Несбалансированные inline math delimiters `$`.")
    if content.count(r"\[") != content.count(r"\]"):
        errors.append("Несбалансированные display math delimiters \\[ и \\].")
    if content.count(r"\(") != content.count(r"\)"):
        errors.append("Несбалансированные inline math delimiters \\( и \\).")


def validate_latex_document(content: str, *, safe_mode: bool = False) -> dict[str, object]:
    """Perform fast structural validation before inserting or compiling generated LaTeX."""
    errors: list[str] = []
    warnings: list[str] = []
    stripped = content.strip()

    if not stripped:
        errors.append("LaTeX-код пуст.")
        return {"valid": False, "errors": errors, "warnings": warnings}

    if not stripped.startswith(r"\documentclass"):
        errors.append("Документ должен начинаться с \\documentclass.")

    if r"\end{document}" not in stripped:
        errors.append("Документ должен содержать \\end{document}.")
    elif not stripped.endswith(r"\end{document}"):
        warnings.append("После \\end{document} найден дополнительный текст; проверьте ответ модели.")

    if "```" in stripped:
        errors.append("LaTeX-код не должен содержать markdown fenced-блоки ```.")

    documentclass_match = re.search(r"\\documentclass(?:\[[^\]]*\])?\{([^}]+)\}", stripped)
    if documentclass_match:
        document_class = documentclass_match.group(1)
        if document_class != "article":
            warnings.append("Ожидался documentclass article для A4-пособия.")
    else:
        errors.append("Не найдена корректная команда \\documentclass{...}.")

    for pattern, message in FORBIDDEN_LATEX_PATTERNS.items():
        if re.search(pattern, stripped):
            errors.append(message)

    body = _extract_document_body(stripped)
    for pattern, message in BODY_FORBIDDEN_LATEX_PATTERNS.items():
        if re.search(pattern, body):
            errors.append(message)

    if safe_mode:
        for pattern, message in SAFE_MODE_FORBIDDEN_BODY_PATTERNS.items():
            if re.search(pattern, body):
                errors.append(message)

    _append_environment_balance_errors(stripped, errors)
    _append_math_delimiter_errors(body, errors)

    for package in REQUIRED_LATEX_PACKAGES:
        if re.search(rf"\\usepackage(?:\[[^\]]*\])?\{{{re.escape(package)}\}}", stripped) is None:
            warnings.append(f"Рекомендуемый пакет {package} не найден.")

    if re.search(r"\\begin\{longtable\}\{[^}]*X[^}]*\}", stripped):
        errors.append("Внутри longtable запрещен тип столбца X; используйте p{...}.")

    if "Cheat Sheet" in stripped:
        warnings.append("В документе найдено 'Cheat Sheet'; предпочтительно использовать 'Итоговая сводка'.")

    return {"valid": not errors, "errors": errors, "warnings": warnings}
