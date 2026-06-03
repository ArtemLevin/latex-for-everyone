import re


FORBIDDEN_LATEX_PATTERNS = {
    r"\\uppercase\b": "Запрещена команда \\uppercase.",
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


def validate_latex_document(content: str) -> dict[str, object]:
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

    for package in REQUIRED_LATEX_PACKAGES:
        if re.search(rf"\\usepackage(?:\[[^\]]*\])?\{{{re.escape(package)}\}}", stripped) is None:
            warnings.append(f"Рекомендуемый пакет {package} не найден.")

    if re.search(r"\\begin\{longtable\}\{[^}]*X[^}]*\}", stripped):
        errors.append("Внутри longtable запрещен тип столбца X; используйте p{...}.")

    if "Cheat Sheet" in stripped:
        warnings.append("В документе найдено 'Cheat Sheet'; предпочтительно использовать 'Итоговая сводка'.")

    return {"valid": not errors, "errors": errors, "warnings": warnings}
