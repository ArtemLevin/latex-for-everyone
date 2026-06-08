import subprocess
import tempfile
import uuid
import shutil
import logging
from pathlib import Path
from typing import Optional
from app.config import settings
from app.schemas import PDFGenerationResult
from app.services.artifact_cleanup import cleanup_old_files
from app.services.artifact_paths import export_root
from app.services.latex_file_policy import enforce_latex_file_policy, parse_allowed_extensions
from app.services.latex_sanitizer import sanitize_latex_files, sanitize_latex_source

logger = logging.getLogger(__name__)


class PDFGenerator:
    def __init__(self):
        self.compiler = settings.LATEX_COMPILER
        self.timeout = settings.COMPILE_TIMEOUT
        self.output_dir = export_root()
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_pdf(
        self,
        main_content: str,
        files: Optional[dict[str, str]] = None,
    ) -> PDFGenerationResult:
        """Generate PDF and save to output directory."""
        compile_id = str(uuid.uuid4())

        with tempfile.TemporaryDirectory() as tmpdir:
            work_dir = Path(tmpdir)

            allowed_extensions = parse_allowed_extensions(settings.LATEX_ALLOWED_EXTENSIONS)
            safe_files = enforce_latex_file_policy(files or {}, allowed_extensions=allowed_extensions)
            sanitized_files = sanitize_latex_files(safe_files)
            sanitized_main_content = sanitize_latex_source(main_content)

            # Write all files
            for safe_name, content in sanitized_files.items():
                filepath = work_dir / safe_name
                filepath.parent.mkdir(parents=True, exist_ok=True)
                filepath.write_text(content, encoding="utf-8")

            main_file = work_dir / "main.tex"
            if not main_file.exists():
                main_file.write_text(sanitized_main_content, encoding="utf-8")

            # Compile
            for run in range(2):
                try:
                    result = subprocess.run(
                        [
                            self.compiler,
                            "-interaction=nonstopmode",
                            "-halt-on-error",
                            "-output-directory", str(work_dir),
                            "main.tex",
                        ],
                        cwd=str(work_dir),
                        capture_output=True,
                        text=True,
                        timeout=self.timeout,
                    )

                    if result.returncode != 0:
                        log_file = work_dir / "main.log"
                        error_text = ""
                        if log_file.exists():
                            error_text = self._truncate_output(log_file.read_text())
                        return PDFGenerationResult(
                            success=False,
                            error=f"Compilation failed:\n{error_text}",
                        )

                except subprocess.TimeoutExpired:
                    return PDFGenerationResult(
                        success=False,
                        error=f"Compilation timed out after {self.timeout}s",
                    )

            # Save PDF
            pdf_file = work_dir / "main.pdf"
            if pdf_file.exists():
                cleanup_old_files(
                    self.output_dir,
                    max_age_seconds=settings.ARTIFACT_TTL_SECONDS,
                    suffixes={".pdf", ".html", ".zip"},
                    trusted_roots=(self.output_dir,),
                )
                pdf_filename = f"{compile_id}.pdf"
                pdf_dest = self.output_dir / pdf_filename
                shutil.copy2(pdf_file, pdf_dest)

                return PDFGenerationResult(
                    success=True,
                    filename=pdf_filename,
                    size=pdf_dest.stat().st_size,
                )

            return PDFGenerationResult(
                success=False,
                error="PDF was not generated",
            )

    def _truncate_output(self, text: str) -> str:
        """Bound compiler output exposed through export errors."""
        limit = settings.MAX_COMPILER_OUTPUT_CHARS
        if limit <= 0 or len(text) <= limit:
            return text
        return text[-limit:]

    def generate_html(self, latex_content: str) -> str:
        """Convert LaTeX to HTML (basic conversion)."""
        import re

        html = latex_content

        # Remove preamble
        html = re.sub(r'\\documentclass\{[^}]+\}.*?\\begin\{document\}', '', html, flags=re.DOTALL)
        html = re.sub(r'\\end\{document\}.*$', '', html, flags=re.DOTALL)

        # Convert sections
        html = re.sub(r'\\section\*?\{([^}]*)\}', r'<h2>\1</h2>', html)
        html = re.sub(r'\\subsection\*?\{([^}]*)\}', r'<h3>\1</h3>', html)

        # Convert text formatting
        html = re.sub(r'\\textbf\{([^}]*)\}', r'<strong>\1</strong>', html)
        html = re.sub(r'\\textit\{([^}]*)\}', r'<em>\1</em>', html)
        html = re.sub(r'\\underline\{([^}]*)\}', r'<u>\1</u>', html)

        # Convert lists
        html = re.sub(r'\\begin\{itemize\}', '<ul>', html)
        html = re.sub(r'\\end\{itemize\}', '</ul>', html)
        html = re.sub(r'\\begin\{enumerate\}', '<ol>', html)
        html = re.sub(r'\\end\{enumerate\}', '</ol>', html)
        html = re.sub(r'\\item\s*', '<li>', html)
        html = re.sub(r'</li>', '</li>', html)

        # Convert display math
        html = re.sub(r'\$\$(.*?)\$\$', r'<div class="equation">\1</div>', html, flags=re.DOTALL)

        # Convert inline math
        html = re.sub(r'\$(.*?)\$', r'<code class="inline-math">\1</code>', html)

        # Clean up
        html = html.replace('\n\n', '</p><p>')
        html = html.replace('\\maketitle', '')
        html = html.replace('\\tableofcontents', '')

        return f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LaTeX Document</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css">
    <script src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js"></script>
    <style>
        body {{ font-family: Georgia, serif; max-width: 700px; margin: 40px auto; padding: 0 20px; line-height: 1.7; }}
        h1 {{ text-align: center; font-size: 2em; }}
        h2 {{ font-size: 1.5em; margin-top: 1.5em; }}
        h3 {{ font-size: 1.25em; margin-top: 1em; }}
        .equation {{ text-align: center; margin: 1.5em 0; }}
        .inline-math {{ font-family: 'Times New Roman', serif; font-style: italic; }}
        ul, ol {{ padding-left: 2em; }}
        li {{ margin: 0.3em 0; }}
    </style>
</head>
<body>
{html}
<script>
    document.addEventListener('DOMContentLoaded', function() {{
        renderMathInElement(document.body, {{
            delimiters: [
                {{left: '$$', right: '$$', display: true}},
                {{left: '$', right: '$', display: false}},
            ],
            throwOnError: false
        }});
    }});
</script>
</body>
</html>"""
