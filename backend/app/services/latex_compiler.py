import subprocess
import os
import time
import shutil
import logging
from pathlib import Path
from typing import Optional
from app.config import settings
from app.schemas import LatexCompileResult

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
    ) -> LatexCompileResult:
        """Compile a LaTeX document into a typed service result."""
        start_time = time.time()
        compile_id = f"compile_{int(time.time())}_{os.getpid()}"
        work_dir = self.work_dir / compile_id

        try:
            work_dir.mkdir(parents=True, exist_ok=True)

            # Write all files
            if files:
                for filename, content in files.items():
                    # Sanitize filename
                    safe_name = Path(filename).name
                    filepath = work_dir / safe_name
                    filepath.write_text(content, encoding="utf-8")

            # Write main file
            main_file = work_dir / "main.tex"
            if not main_file.exists():
                main_file.write_text(main_content, encoding="utf-8")

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
                            "main.tex",
                        ],
                        cwd=str(work_dir),
                        capture_output=True,
                        text=True,
                        timeout=self.timeout,
                    )
                    log_output.append(result.stdout)

                    if result.returncode != 0:
                        # Check for errors in log
                        log_file = work_dir / "main.log"
                        if log_file.exists():
                            log_text = log_file.read_text()
                            errors = self._extract_errors(log_text)
                            if errors:
                                compile_time = f"{time.time() - start_time:.2f}s"
                                return LatexCompileResult(
                                    status="error",
                                    error=errors,
                                    output=log_text[-2000:],
                                    compile_time=compile_time,
                                )

                        compile_time = f"{time.time() - start_time:.2f}s"
                        return LatexCompileResult(
                            status="error",
                            error=f"Compilation failed on run {run + 1}",
                            output=result.stdout[-2000:],
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
            pdf_file = work_dir / "main.pdf"
            pdf_url = None

            if pdf_file.exists():
                # Save PDF for download
                output_dir = self.work_dir / "pdfs"
                output_dir.mkdir(parents=True, exist_ok=True)

                pdf_filename = f"{compile_id}.pdf"
                pdf_dest = output_dir / pdf_filename
                shutil.copy2(pdf_file, pdf_dest)
                pdf_url = f"/api/compile/download/{pdf_filename}"

            compile_time = f"{time.time() - start_time:.2f}s"

            return LatexCompileResult(
                status="success",
                output=log_output[-1] if log_output else "",
                compile_time=compile_time,
                pdf_url=pdf_url,
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
