from app.config import settings
from app.services.compile_runners.base import CompileInput, CompileOutput, CompileRunner
from app.services.compile_runners.docker_sandbox import DockerSandboxCompileRunner
from app.services.compile_runners.local_subprocess import LocalSubprocessCompileRunner


def create_compile_runner() -> CompileRunner:
    mode = settings.COMPILE_EXECUTION_MODE.strip().lower()
    if mode == "sandbox":
        return DockerSandboxCompileRunner()
    if mode == "local_subprocess":
        return LocalSubprocessCompileRunner()
    raise ValueError("COMPILE_EXECUTION_MODE must be sandbox or local_subprocess")


__all__ = [
    "CompileInput",
    "CompileOutput",
    "CompileRunner",
    "DockerSandboxCompileRunner",
    "LocalSubprocessCompileRunner",
    "create_compile_runner",
]
