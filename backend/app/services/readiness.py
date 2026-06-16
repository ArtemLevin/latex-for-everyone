import shutil
import subprocess
import tempfile
from datetime import timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, inspect, text
from sqlalchemy import func

from app.config import settings
from app.database import Base, SessionLocal, engine as default_engine
from app.models import GenerationJob
from app.schemas import ReadinessCheckResponse, ReadinessResponse
from app.services.ai_request_control import RequestControlBackendError, build_ai_request_control_service
from app.services.transcription import get_transcription_runtime_status
from app.time_utils import utc_now

REQUIRED_TABLES = frozenset(Base.metadata.tables.keys())
LATEX_PACKAGE_FILES = {
    "russian_ldf": "russian.ldf",
    "t2aenc_def": "t2aenc.def",
}
KPSEWHICH_TIMEOUT_SECONDS = 3

def _check_response(status: str, message: str, details: dict[str, Any] | None = None) -> ReadinessCheckResponse:
    return ReadinessCheckResponse(status=status, message=message, details=details or {})

def check_database_ready(db_engine: Engine = default_engine) -> ReadinessCheckResponse:
    """Check that the database is reachable and contains the expected app tables."""
    try:
        with db_engine.connect() as connection:
            connection.execute(text("SELECT 1"))

        inspector = inspect(db_engine)
        existing_tables = set(inspector.get_table_names())
        missing_tables = sorted(REQUIRED_TABLES - existing_tables)
        details = {
            "required_tables": sorted(REQUIRED_TABLES),
            "missing_tables": missing_tables,
            "required_tables_present": not missing_tables,
            "alembic_version_present": "alembic_version" in existing_tables,
        }
        if missing_tables:
            return _check_response("error", "Database is reachable but required tables are missing", details)
        return _check_response("ok", "Database connection is available", details)
    except Exception as exc:  # noqa: BLE001 - readiness should report failures instead of raising
        return _check_response("error", "Database readiness check failed", {"error": str(exc)})

def check_compiler_ready() -> ReadinessCheckResponse:
    """Check whether the configured LaTeX compiler binary can be found on PATH."""
    compiler = settings.LATEX_COMPILER
    compiler_path = shutil.which(compiler)
    details = {"binary": compiler, "path": compiler_path}
    if not compiler_path:
        return _check_response("missing", f"{compiler} was not found on PATH", details)
    return _check_response("ok", f"{compiler} found", details)

def _kpsewhich_exists(filename: str) -> bool:
    result = subprocess.run(
        ["kpsewhich", filename],
        check=False,
        capture_output=True,
        text=True,
        timeout=KPSEWHICH_TIMEOUT_SECONDS,
    )
    return result.returncode == 0 and bool(result.stdout.strip())

def check_latex_packages_ready(compiler_check: ReadinessCheckResponse | None = None) -> ReadinessCheckResponse:
    """Check Russian babel/T2A package availability when the compiler is installed."""
    if compiler_check is not None and compiler_check.status != "ok":
        return _check_response(
            "skipped",
            "LaTeX package checks skipped because the compiler is unavailable",
            {"reason": compiler_check.status},
        )

    kpsewhich_path = shutil.which("kpsewhich")
    if not kpsewhich_path:
        return _check_response(
            "missing",
            "kpsewhich was not found on PATH",
            {"binary": "kpsewhich", "path": None},
        )

    try:
        package_status = {key: _kpsewhich_exists(filename) for key, filename in LATEX_PACKAGE_FILES.items()}
    except subprocess.TimeoutExpired as exc:
        return _check_response(
            "error",
            "LaTeX package readiness check timed out",
            {"binary": "kpsewhich", "timeout_seconds": KPSEWHICH_TIMEOUT_SECONDS, "error": str(exc)},
        )
    except OSError as exc:
        return _check_response(
            "error",
            "LaTeX package readiness check failed",
            {"binary": "kpsewhich", "error": str(exc)},
        )

    details = {"binary": "kpsewhich", "path": kpsewhich_path, **package_status}
    missing = [LATEX_PACKAGE_FILES[key] for key, available in package_status.items() if not available]
    if missing:
        details["missing_packages"] = missing
        return _check_response("missing", "Russian/T2A LaTeX support is incomplete", details)

    return _check_response("ok", "Russian/T2A LaTeX support is available", details)

def _check_directory_writable(directory: Path) -> dict[str, Any]:
    resolved = directory.resolve()
    resolved.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix=".latexed_ready_", dir=resolved, delete=True) as probe:
        probe.write(b"ok")
        probe.flush()
    return {"status": "ok", "path": str(resolved)}

def check_artifact_dirs_ready() -> ReadinessCheckResponse:
    """Check that runtime artifact directories exist and are writable."""
    directories = {
        "compile_work_dir": Path(settings.COMPILE_WORK_DIR),
        "compile_pdf_dir": Path(settings.COMPILE_WORK_DIR) / "pdfs",
        "upload_dir": Path(settings.UPLOAD_DIR),
        "export_dir": Path(settings.UPLOAD_DIR) / "exports",
    }
    details: dict[str, Any] = {}
    failed: dict[str, str] = {}

    for name, directory in directories.items():
        try:
            details[name] = _check_directory_writable(directory)
        except OSError as exc:
            details[name] = {"status": "error", "path": str(directory), "error": str(exc)}
            failed[name] = str(exc)

    if failed:
        return _check_response("error", "One or more runtime artifact directories are not writable", details)
    return _check_response("ok", "Runtime artifact directories are writable", details)

def check_transcription_ready() -> ReadinessCheckResponse:
    """Check optional lesson transcription runtime without loading Whisper models."""
    status = get_transcription_runtime_status()
    return _check_response(str(status["status"]), str(status["message"]), dict(status["details"]))

def check_ai_request_control_ready() -> ReadinessCheckResponse:
    """Check whether the configured AI request-control backend can be reached."""
    try:
        details = build_ai_request_control_service().health_check()
    except (RequestControlBackendError, ValueError) as exc:
        return _check_response("error", "AI request-control backend is unavailable", {"error": str(exc)})
    backend = str(details.get("backend", "memory"))
    if backend == "memory":
        return _check_response("ok", "AI request control uses process-local memory", details)
    return _check_response("ok", "AI request control shared backend is available", details)


def check_generation_jobs_ready(session_factory=SessionLocal) -> ReadinessCheckResponse:
    """Report generation worker backlog and stale running jobs without exposing prompts."""
    db = session_factory()
    try:
        rows = db.query(GenerationJob.status, func.count(GenerationJob.id)).group_by(GenerationJob.status).all()
        counts = {status: count for status, count in rows}
        details: dict[str, Any] = {
            "execution_mode": settings.AI_GENERATION_JOB_EXECUTION_MODE,
            "stale_after_seconds": settings.AI_GENERATION_JOB_STALE_AFTER_SECONDS,
            "counts": {
                "queued": counts.get("queued", 0),
                "running": counts.get("running", 0),
                "completed": counts.get("completed", 0),
                "failed": counts.get("failed", 0),
                "canceled": counts.get("canceled", 0),
            },
        }
        stale_running = 0
        if settings.AI_GENERATION_JOB_STALE_AFTER_SECONDS > 0:
            cutoff = utc_now() - timedelta(seconds=settings.AI_GENERATION_JOB_STALE_AFTER_SECONDS)
            stale_running = (
                db.query(func.count(GenerationJob.id))
                .filter(GenerationJob.status == "running", GenerationJob.updated_at < cutoff)
                .scalar()
                or 0
            )
        details["stale_running"] = stale_running
        details["backlog"] = details["counts"]["queued"] + details["counts"]["running"]
        if stale_running:
            return _check_response("error", "Generation worker has stale running jobs", details)
        return _check_response("ok", "Generation job backlog is observable", details)
    except Exception as exc:  # noqa: BLE001 - readiness should report failures instead of raising
        return _check_response("error", "Generation job readiness check failed", {"error": str(exc)})
    finally:
        db.close()

def aggregate_readiness_status(checks: dict[str, ReadinessCheckResponse]) -> str:
    """Aggregate individual readiness checks into ready/degraded/not_ready."""
    if checks["database"].status != "ok" or checks["artifact_dirs"].status != "ok":
        return "not_ready"
    if checks["compiler"].status != "ok" or checks["latex_packages"].status not in {"ok", "skipped"}:
        return "degraded"
    if checks["latex_packages"].status == "skipped" and checks["compiler"].status != "ok":
        return "degraded"
    if checks.get("transcription") and checks["transcription"].status not in {"ok", "skipped"}:
        return "degraded"
    if checks.get("generation_jobs") and checks["generation_jobs"].status != "ok":
        return "degraded"
    if checks.get("ai_request_control") and checks["ai_request_control"].status != "ok":
        return "degraded"
    return "ready"

def build_readiness_response(db_engine: Engine = default_engine) -> ReadinessResponse:
    """Run all readiness checks and return the public API response model."""
    database = check_database_ready(db_engine)
    compiler = check_compiler_ready()
    latex_packages = check_latex_packages_ready(compiler)
    artifact_dirs = check_artifact_dirs_ready()
    transcription = check_transcription_ready()
    generation_jobs = check_generation_jobs_ready()
    ai_request_control = check_ai_request_control_ready()
    checks = {
        "database": database,
        "compiler": compiler,
        "latex_packages": latex_packages,
        "artifact_dirs": artifact_dirs,
        "transcription": transcription,
        "generation_jobs": generation_jobs,
        "ai_request_control": ai_request_control,
    }
    return ReadinessResponse(status=aggregate_readiness_status(checks), checks=checks)
