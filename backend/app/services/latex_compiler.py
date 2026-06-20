import logging
from pathlib import Path

from app.config import settings
from app.schemas import LatexCompileResult
from app.services.compile_runners.base import CompileInput
from app.services.compile_runners.local_subprocess import LocalSubprocessCompileRunner

logger = logging.getLogger(__name__)


class LatexCompiler:
    """Legacy compile facade kept for direct/dev synchronous compilation.

    New persisted compile jobs use the configured sandbox runner in the compile
    worker. This facade preserves historical tests and development behavior while
    still enforcing -no-shell-escape in the local subprocess runner.
    """

    def __init__(self):
        self.compiler = settings.LATEX_COMPILER
        self.timeout = settings.COMPILE_TIMEOUT
        self.work_dir = Path(settings.COMPILE_WORK_DIR)

    def compile(
        self,
        main_content: str,
        files: dict[str, str] | None = None,
        main_filename: str = "main.tex",
    ) -> LatexCompileResult:
        # compile_{uuid.uuid4().hex} remains in the concrete local runner.
        runner = LocalSubprocessCompileRunner()
        runner.compiler = self.compiler
        runner.timeout = self.timeout
        runner.work_dir = self.work_dir
        output = runner.compile(
            CompileInput(main_content=main_content, files=files or {}, main_filename=main_filename or "main.tex")
        )
        return LatexCompileResult(
            status=output.status,
            output=output.output,
            error=output.error,
            compile_time=output.compile_time,
            pdf_url=f"/api/compile/download/{output.pdf_filename}" if output.pdf_filename else None,
            pdf_filename=output.pdf_filename,
        )

    def _truncate_output(self, text: str) -> str:
        return LocalSubprocessCompileRunner()._truncate_output(text)

    def _extract_errors(self, log_text: str) -> str:
        return LocalSubprocessCompileRunner()._extract_errors(log_text)


class LiveCompiler:
    """For WebSocket-based live compilation."""

    def __init__(self):
        self.active_compilations = {}

    async def compile_stream(self, content: str, callback) -> None:
        compiler = LatexCompiler()
        result = compiler.compile(content, {})
        await callback(result.model_dump())
