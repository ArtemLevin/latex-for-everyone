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


class DockerSandboxCompileRunner:
    """Run each LaTeX compile in a hardened one-shot Docker container."""

    def __init__(self) -> None:
        self.sandbox_root = Path(settings.COMPILE_SANDBOX_ROOT)

    def build_docker_command(
        self, *, input_dir: Path, output_dir: Path, main_filename: str, container_name: str
    ) -> list[str]:
        command = [
            "docker",
            "run",
            "--rm",
            "--name",
            container_name,
            "--network",
            "none" if settings.COMPILE_SANDBOX_NETWORK_DISABLED else "bridge",
            "--user",
            f"{settings.COMPILE_SANDBOX_UID}:{settings.COMPILE_SANDBOX_GID}",
            "--workdir",
            "/work/input",
            "--memory",
            settings.COMPILE_SANDBOX_MEMORY,
            "--memory-swap",
            settings.COMPILE_SANDBOX_MEMORY,
            "--cpus",
            str(settings.COMPILE_SANDBOX_CPUS),
            "--pids-limit",
            str(settings.COMPILE_SANDBOX_PIDS_LIMIT),
            "--tmpfs",
            f"/tmp:size={settings.COMPILE_SANDBOX_TMPFS_SIZE},mode=1777",
            "--mount",
            f"type=bind,source={input_dir},target=/work/input,readonly",
            "--mount",
            f"type=bind,source={output_dir},target=/work/out",
            "--env",
            f"openin_any={settings.COMPILE_SANDBOX_OPENIN_ANY}",
            "--env",
            f"openout_any={settings.COMPILE_SANDBOX_OPENOUT_ANY}",
            "--env",
            "shell_escape=f",
            "--label",
            f"latexed.compile_job={container_name}",
        ]
        if settings.COMPILE_SANDBOX_READ_ONLY_ROOTFS:
            command.append("--read-only")
        if settings.COMPILE_SANDBOX_CAP_DROP_ALL:
            command.extend(["--cap-drop", "ALL"])
        security_opts: list[str] = []
        if settings.COMPILE_SANDBOX_NO_NEW_PRIVILEGES:
            security_opts.append("no-new-privileges:true")
        if settings.COMPILE_SANDBOX_SECCOMP_PROFILE and settings.COMPILE_SANDBOX_SECCOMP_PROFILE != "default":
            security_opts.append(f"seccomp={settings.COMPILE_SANDBOX_SECCOMP_PROFILE}")
        if settings.COMPILE_SANDBOX_APPARMOR_PROFILE:
            security_opts.append(f"apparmor={settings.COMPILE_SANDBOX_APPARMOR_PROFILE}")
        for opt in security_opts:
            command.extend(["--security-opt", opt])
        command.extend([settings.COMPILE_SANDBOX_IMAGE, main_filename])
        return command

    def compile(self, compile_input: CompileInput) -> CompileOutput:
        start_time = time.time()
        compile_id = f"compile_{uuid.uuid4().hex}"
        job_root = self.sandbox_root / compile_id
        input_dir = job_root / "input"
        output_dir = job_root / "out"
        try:
            safe_main_name = self._write_inputs(input_dir, compile_input)
            output_dir.mkdir(parents=True, exist_ok=True)
            command = self.build_docker_command(
                input_dir=input_dir.resolve(),
                output_dir=output_dir.resolve(),
                main_filename=safe_main_name,
                container_name=compile_id,
            )
            logger.info(
                "starting latex sandbox container compile_id=%s image=%s", compile_id, settings.COMPILE_SANDBOX_IMAGE
            )
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=settings.COMPILE_SANDBOX_TIMEOUT_SECONDS,
            )
            output = "\n".join(part for part in [result.stdout, result.stderr] if part)
            if result.returncode != 0:
                return CompileOutput(
                    status="error",
                    error=f"Sandboxed compilation failed with exit code {result.returncode}",
                    output=self._truncate_output(output),
                    compile_time=f"{time.time() - start_time:.2f}s",
                    raw_log_path=output_dir / f"{Path(safe_main_name).stem}.log",
                )
            output_size = self._directory_size(output_dir)
            if output_size > settings.COMPILE_SANDBOX_OUTPUT_SIZE_BYTES:
                return CompileOutput(
                    status="error",
                    error="Sandboxed compilation output exceeded size limit",
                    output=self._truncate_output(output),
                    compile_time=f"{time.time() - start_time:.2f}s",
                )
            pdf_file = output_dir / f"{Path(safe_main_name).stem}.pdf"
            pdf_filename = None
            if pdf_file.exists():
                artifact_root = compile_pdf_root()
                artifact_root.mkdir(parents=True, exist_ok=True)
                cleanup_old_files(
                    artifact_root,
                    max_age_seconds=settings.ARTIFACT_TTL_SECONDS,
                    suffixes={".pdf"},
                    trusted_roots=(artifact_root,),
                )
                pdf_filename = f"{compile_id}.pdf"
                shutil.copy2(pdf_file, artifact_root / pdf_filename)
            return CompileOutput(
                status="success",
                output=self._truncate_output(output),
                compile_time=f"{time.time() - start_time:.2f}s",
                pdf_path=compile_pdf_root() / pdf_filename if pdf_filename else None,
                pdf_filename=pdf_filename,
                raw_log_path=output_dir / f"{Path(safe_main_name).stem}.log",
            )
        except subprocess.TimeoutExpired:
            subprocess.run(["docker", "rm", "-f", compile_id], capture_output=True, text=True, timeout=10)
            return CompileOutput(
                status="error",
                error=f"Sandboxed compilation timed out after {settings.COMPILE_SANDBOX_TIMEOUT_SECONDS}s",
                compile_time=f"{time.time() - start_time:.2f}s",
            )
        except Exception as exc:
            logger.error("sandboxed LaTeX compilation failed: %s", exc, exc_info=True)
            return CompileOutput(status="error", error=str(exc), compile_time=f"{time.time() - start_time:.2f}s")
        finally:
            if job_root.exists() and not settings.COMPILE_SANDBOX_KEEP_FAILED_WORKDIR:
                shutil.rmtree(job_root, ignore_errors=True)

    def _write_inputs(self, input_dir: Path, compile_input: CompileInput) -> str:
        input_dir.mkdir(parents=True, exist_ok=True)
        allowed_extensions = parse_allowed_extensions(settings.LATEX_ALLOWED_EXTENSIONS)
        safe_files = enforce_latex_file_policy(compile_input.files or {}, allowed_extensions=allowed_extensions)
        sanitized_files = sanitize_latex_files(safe_files)
        safe_main_name = validate_latex_filename(
            compile_input.main_filename or "main.tex", allowed_extensions=allowed_extensions
        )
        for safe_name, content in sanitized_files.items():
            path = input_dir / safe_name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        main_file = input_dir / safe_main_name
        main_file.parent.mkdir(parents=True, exist_ok=True)
        main_file.write_text(sanitize_latex_source(compile_input.main_content), encoding="utf-8")
        return safe_main_name

    def _directory_size(self, path: Path) -> int:
        return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())

    def _truncate_output(self, text: str) -> str:
        limit = settings.MAX_COMPILER_OUTPUT_CHARS
        if limit <= 0 or len(text) <= limit:
            return text
        return text[-limit:]
