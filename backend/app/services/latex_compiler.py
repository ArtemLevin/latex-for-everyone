import subprocess
import time
import uuid
import shutil
import logging
from pathlib import Path
from typing import Optional
from app.config import settings
from app.schemas import LatexCompileResult
from app.services.artifact_cleanup import cleanup_old_files
from app.services.artifact_paths import compile_pdf_root
from app.services.latex_file_policy import enforce_latex_file_policy, parse_allowed_extensions, validate_latex_filename
from app.services.latex_sanitizer import sanitize_latex_files, sanitize_latex_source

logger = logging.getLogger(__name__)


class LatexCompiler:
    def __init__(self):
        self.compiler = settings.LATEX_COMPILER
        self.timeout = settings.COMPILE_TIMEOUT
        self.work_dir = Path(settings.COMPILE_WORK_DIR)

    def compile(
        self,
        main_content: str,
        files: Optional[dict[str, str]] = None,
        main_filename: str = "main.tex",
    ) -> LatexCompileResult:
        """Compile a LaTeX document into a typed service result."""
        start_time = time.time()
        compile_id = f"compile_{uuid.uuid4().hex}"
        work_dir = self.work_dir / compile_id

        try:
            work_dir.mkdir(parents=True, exist_ok=True)

            allowed_extensions = parse_allowed_extensions(settings.LATEX_ALLOWED_EXTENSIONS)
            safe_files = enforce_latex_file_policy(files or {}, allowed_extensions=allowed_extensions)
            sanitized_files = sanitize_latex_files(safe_files)
            sanitized_main_content = sanitize_latex_source(main_content)
            safe_main_name = validate_latex_filename(
                main_filename or "main.tex",
                allowed_extensions=allowed_extensions,
            )

            # Write all files
            for safe_name, content in sanitized_files.items():
                filepath = work_dir / safe_name
                filepath.parent.mkdir(parents=True, exist_ok=True)
                filepath.write_text(content, encoding="utf-8")

            # Always write the selected compile entrypoint last so request overrides
            # cannot be shadowed by a same-named project file already in all_files.
            main_file = work_dir / safe_main_name
            main_file.parent.mkdir(parents=True, exist_ok=True)
            main_file.write_text(sanitized_main_content, encoding="utf-8")

            # Compile with pdflatex (run twice for references)
            log_output: list[str] = []

            for run in range(2):
                try:
                    result = subprocess.run(
                        [
                            self.compiler,
                            "-interaction=nonstopmode",
                            "-halt-on-error",
                            "-output-directory", str(work_dir),
                            safe_main_name,
                        ],
                        cwd=str(work_dir),
                        capture_output=True,
                        text=True,
                        timeout=self.timeout,
                    )
                    log_output.append(result.stdout)

                    if result.returncode != 0:
                        # Check for errors in log
                        log_file = work_dir / f"{Path(safe_main_name).stem}.log"
                        if log_file.exists():
                            log_text = log_file.read_text()
                            errors = self._extract_errors(log_text)
                            if errors:
                                compile_time = f"{time.time() - start_time:.2f}s"
                                return LatexCompileResult(
                                    status="error",
                                    error=errors,
                                    output=self._truncate_output(log_text),
                                    compile_time=compile_time,
                                )

                        compile_time = f"{time.time() - start_time:.2f}s"
                        return LatexCompileResult(
                            status="error",
                            error=f"Compilation failed on run {run + 1}",
                            output=self._truncate_output(result.stdout),
                            compile_time=compile_time,
                        )

                except subprocess.TimeoutExpired:
                    compile_time = f"{time.time() - start_time:.2f}s"
                    return LatexCompileResult(
                        status="error",
                        error=f"Compilation timed out after {self.timeout}s",
                        compile_time=compile_time,
                    )

            # Check if PDF was generated
            pdf_file = work_dir / f"{Path(safe_main_name).stem}.pdf"
            pdf_url = None

            if pdf_file.exists():
                # Save PDF for download
                output_dir = compile_pdf_root()
                output_dir.mkdir(parents=True, exist_ok=True)
                cleanup_old_files(
                    output_dir,
                    max_age_seconds=settings.ARTIFACT_TTL_SECONDS,
                    suffixes={".pdf"},
                    trusted_roots=(output_dir,),
                )

                pdf_filename = f"{compile_id}.pdf"
                pdf_dest = output_dir / pdf_filename
                shutil.copy2(pdf_file, pdf_dest)
                pdf_url = f"/api/compile/download/{pdf_filename}"

            compile_time = f"{time.time() - start_time:.2f}s"

            return LatexCompileResult(
                status="success",
                output=self._truncate_output(log_output[-1]) if log_output else "",
                compile_time=compile_time,
                pdf_url=pdf_url,
                pdf_filename=pdf_filename if pdf_url else None,
            )

        except Exception as e:
            logger.error(f"Compilation error: {e}", exc_info=True)
            compile_time = f"{time.time() - start_time:.2f}s"
            return LatexCompileResult(
                status="error",
                error=str(e),
                compile_time=compile_time,
            )

        finally:
            # Cleanup work directory
            if work_dir.exists():
                shutil.rmtree(work_dir, ignore_errors=True)

    def _truncate_output(self, text: str) -> str:
        """Bound compiler output stored in API responses and compile history."""
        limit = settings.MAX_COMPILER_OUTPUT_CHARS
        if limit <= 0 or len(text) <= limit:
            return text
        return text[-limit:]

    def _extract_errors(self, log_text: str) -> str:
        """Extract error messages from LaTeX log."""
        errors: list[str] = []
        lines = log_text.split("\n")

        for i, line in enumerate(lines):
            if line.startswith("!"):
                # Get error message and context
                error_msg = line
                if i + 1 < len(lines):
                    error_msg += "\n" + lines[i + 1]
                errors.append(error_msg)

        self._append_environment_hints(log_text, errors)

        if errors:
            return "\n".join(errors[:10])  # Return first 10 errors

        # Check for undefined references
        if "There were undefined references" in log_text:
            errors.append("Warning: There were undefined references")

        if "Rerun to get cross-references right" in log_text:
            errors.append("Warning: Rerun needed for cross-references")

        return "\n".join(errors)

    def _append_environment_hints(self, log_text: str, errors: list[str]) -> None:
        """Append actionable hints for common missing TeX Live packages."""
        lower_log = log_text.lower()
        if "unknown option `list=true'" in lower_log and "enumitem" in lower_log:
            errors.append(
                "LaTeX source hint: enumitem does not support package option list=true. "
                "Use \\usepackage{enumitem} without list=true; configure lists with \\setlist{...} instead."
            )

        if "font expansion" in lower_log and "only possible with scalable" in lower_log:
            errors.append(
                "LaTeX source hint: pdfTeX font expansion requires scalable fonts. "
                "Use \\usepackage[expansion=false]{microtype} or disable microtype expansion "
                "when compiling T2A/Cyrillic documents."
            )

        if (
            "unknown option 'russian'" in lower_log
            or "unknown option `russian'" in lower_log
            or "russian.ldf" in lower_log
        ):
            errors.append(
                "LaTeX environment hint: package babel cannot load Russian language support. "
                "Install TeX Live Cyrillic language files (Ubuntu/Debian: "
                "sudo apt install texlive-lang-cyrillic) and restart the backend."
            )

        if "t2a" in lower_log and ("fontenc" in lower_log or "encoding file" in lower_log):
            errors.append(
                "LaTeX environment hint: T2A Cyrillic font encoding files are missing. "
                "Install TeX Live Cyrillic support (Ubuntu/Debian: sudo apt install texlive-lang-cyrillic)."
            )


# WebSocket support for live compilation
class LiveCompiler:
    """For WebSocket-based live compilation"""

    def __init__(self):
        self.active_compilations = {}

    async def compile_stream(self, content: str, callback) -> None:
        """Stream compilation results via callback"""
        compiler = LatexCompiler()
        result = compiler.compile(content, {})
        await callback(result.model_dump())
