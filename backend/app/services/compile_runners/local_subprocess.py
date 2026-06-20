import logging
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path

from app.config import settings
from app.services.artifact_cleanup import cleanup_old_files
from app.services.artifact_paths import compile_pdf_root
from app.services.compile_runners.base import CompileInput, CompileOutput
from app.services.latex_file_policy import enforce_latex_file_policy, parse_allowed_extensions, validate_latex_filename
from app.services.latex_sanitizer import sanitize_latex_files, sanitize_latex_source

logger = logging.getLogger(__name__)


class LocalSubprocessCompileRunner:
    """Development/test runner that executes pdflatex as a local subprocess.

    Production deployments must use the Docker sandbox runner; this runner is kept
    for local environments and CI tests that do not have a container runtime.
    """

    def __init__(self) -> None:
        self.compiler = settings.LATEX_COMPILER
        self.timeout = settings.COMPILE_TIMEOUT
        self.work_dir = Path(settings.COMPILE_WORK_DIR)

    def compile(self, compile_input: CompileInput) -> CompileOutput:
        start_time = time.time()
        compile_id = f"compile_{uuid.uuid4().hex}"
        work_dir = self.work_dir / compile_id
        try:
            safe_main_name = self._write_inputs(work_dir, compile_input)
            log_output: list[str] = []
            for run in range(2):
                try:
                    result = subprocess.run(
                        [
                            self.compiler,
                            "-no-shell-escape",
                            "-interaction=nonstopmode",
                            "-halt-on-error",
                            "-file-line-error",
                            "-output-directory",
                            str(work_dir),
                            safe_main_name,
                        ],
                        cwd=str(work_dir),
                        capture_output=True,
                        text=True,
                        timeout=self.timeout,
                        env={
                            **os.environ,
                            "openin_any": settings.COMPILE_SANDBOX_OPENIN_ANY,
                            "openout_any": settings.COMPILE_SANDBOX_OPENOUT_ANY,
                            "shell_escape": "f",
                        },
                    )
                    log_output.append(result.stdout)
                    if result.returncode != 0:
                        return self._error_from_failed_run(work_dir, safe_main_name, run, result.stdout, start_time)
                except subprocess.TimeoutExpired:
                    return CompileOutput(
                        status="error",
                        error=f"Compilation timed out after {self.timeout}s",
                        compile_time=f"{time.time() - start_time:.2f}s",
                    )

            pdf_file = work_dir / f"{Path(safe_main_name).stem}.pdf"
            pdf_filename = None
            if pdf_file.exists():
                output_dir = compile_pdf_root()
                output_dir.mkdir(parents=True, exist_ok=True)
                cleanup_old_files(
                    output_dir,
                    max_age_seconds=settings.ARTIFACT_TTL_SECONDS,
                    suffixes={".pdf"},
                    trusted_roots=(output_dir,),
                )
                pdf_filename = f"{compile_id}.pdf"
                shutil.copy2(pdf_file, output_dir / pdf_filename)

            return CompileOutput(
                status="success",
                output=self._truncate_output(log_output[-1]) if log_output else "",
                compile_time=f"{time.time() - start_time:.2f}s",
                pdf_path=compile_pdf_root() / pdf_filename if pdf_filename else None,
                pdf_filename=pdf_filename,
                raw_log_path=work_dir / f"{Path(safe_main_name).stem}.log",
            )
        except Exception as exc:
            logger.error("local LaTeX compilation failed: %s", exc, exc_info=True)
            return CompileOutput(status="error", error=str(exc), compile_time=f"{time.time() - start_time:.2f}s")
        finally:
            if work_dir.exists() and not settings.COMPILE_SANDBOX_KEEP_FAILED_WORKDIR:
                shutil.rmtree(work_dir, ignore_errors=True)

    def _write_inputs(self, work_dir: Path, compile_input: CompileInput) -> str:
        work_dir.mkdir(parents=True, exist_ok=True)
        allowed_extensions = parse_allowed_extensions(settings.LATEX_ALLOWED_EXTENSIONS)
        safe_files = enforce_latex_file_policy(compile_input.files or {}, allowed_extensions=allowed_extensions)
        sanitized_files = sanitize_latex_files(safe_files)
        safe_main_name = validate_latex_filename(
            compile_input.main_filename or "main.tex", allowed_extensions=allowed_extensions
        )
        for safe_name, content in sanitized_files.items():
            path = work_dir / safe_name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        main_file = work_dir / safe_main_name
        main_file.parent.mkdir(parents=True, exist_ok=True)
        main_file.write_text(sanitize_latex_source(compile_input.main_content), encoding="utf-8")
        return safe_main_name

    def _error_from_failed_run(
        self, work_dir: Path, safe_main_name: str, run: int, stdout: str, start_time: float
    ) -> CompileOutput:
        log_file = work_dir / f"{Path(safe_main_name).stem}.log"
        if log_file.exists():
            log_text = log_file.read_text(errors="replace")
            errors = self._extract_errors(log_text)
            if errors:
                return CompileOutput(
                    status="error",
                    error=errors,
                    output=self._truncate_output(log_text),
                    compile_time=f"{time.time() - start_time:.2f}s",
                    raw_log_path=log_file,
                )
        return CompileOutput(
            status="error",
            error=f"Compilation failed on run {run + 1}",
            output=self._truncate_output(stdout),
            compile_time=f"{time.time() - start_time:.2f}s",
        )

    def _truncate_output(self, text: str) -> str:
        limit = settings.MAX_COMPILER_OUTPUT_CHARS
        if limit <= 0 or len(text) <= limit:
            return text
        return text[-limit:]

    def _extract_errors(self, log_text: str) -> str:
        errors: list[str] = []
        lines = log_text.split("\n")
        for i, line in enumerate(lines):
            if line.startswith("!"):
                error_msg = line
                if i + 1 < len(lines):
                    error_msg += "\n" + lines[i + 1]
                errors.append(error_msg)
        self._append_environment_hints(log_text, errors)
        if "There were undefined references" in log_text:
            errors.append("Warning: There were undefined references")
        if "Rerun to get cross-references right" in log_text:
            errors.append("Warning: Rerun needed for cross-references")
        return "\n".join(errors[:10])

    def _append_environment_hints(self, log_text: str, errors: list[str]) -> None:
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
