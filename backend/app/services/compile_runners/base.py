from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol


@dataclass(frozen=True)
class CompileInput:
    main_content: str
    files: dict[str, str]
    main_filename: str = "main.tex"


@dataclass(frozen=True)
class CompileOutput:
    status: Literal["success", "error"]
    output: str | None = None
    error: str | None = None
    compile_time: str | None = None
    pdf_path: Path | None = None
    pdf_filename: str | None = None
    raw_log_path: Path | None = None


class CompileRunner(Protocol):
    def compile(self, compile_input: CompileInput) -> CompileOutput: ...
