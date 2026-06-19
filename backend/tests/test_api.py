"""
Tests for the Latexed API.
"""
import hashlib
from pathlib import Path
import threading

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import get_db, engine, Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Test database
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_latexed.db"
engine_test = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionTesting = sessionmaker(autocommit=False, autoflush=False, bind=engine_test)


def override_get_db():
    db = SessionTesting()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine_test)
    yield
    Base.metadata.drop_all(bind=engine_test)


client = TestClient(app)


def enable_trusted_proxy_auth(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "AUTH_MODE", "trusted_proxy")
    monkeypatch.setattr(settings, "TRUSTED_PROXY_IPS", ["testclient"])
    monkeypatch.setattr(settings, "TRUSTED_USER_HEADER", "X-Latexed-User")


def test_initialize_database_respects_auto_create_flag(monkeypatch):
    from app import main as main_module
    from app.config import settings

    called = False

    def fake_create_all(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(settings, "AUTO_CREATE_TABLES", False)
    monkeypatch.setattr(main_module.Base.metadata, "create_all", fake_create_all)

    main_module.initialize_database()

    assert called is False


def test_initialize_database_adds_generation_history_token_columns_for_stale_local_db(monkeypatch, tmp_path):
    from sqlalchemy import inspect, text
    from app import main as main_module
    from app.config import settings

    stale_engine = create_engine(f"sqlite:///{tmp_path / 'stale_latexed.db'}")
    with stale_engine.begin() as connection:
        connection.execute(text("CREATE TABLE projects (id VARCHAR(36) PRIMARY KEY, name VARCHAR(255) NOT NULL)"))
        connection.execute(
            text(
                "CREATE TABLE generation_history ("
                "id VARCHAR(36) PRIMARY KEY, "
                "project_id VARCHAR(36), "
                "provider VARCHAR(100) NOT NULL, "
                "model VARCHAR(255), "
                "status VARCHAR(50) NOT NULL, "
                "prompt_hash VARCHAR(64) NOT NULL, "
                "fields JSON NOT NULL"
                ")"
            )
        )

    monkeypatch.setattr(settings, "AUTO_CREATE_TABLES", True)
    monkeypatch.setattr(main_module, "engine", stale_engine)

    main_module.initialize_database()

    columns = {column["name"] for column in inspect(stale_engine).get_columns("generation_history")}
    assert {"owner_id", "input_tokens", "output_tokens", "total_tokens", "token_count_source"}.issubset(columns)


def test_initialize_database_adds_lesson_workflow_columns_for_stale_local_db(monkeypatch, tmp_path):
    from sqlalchemy import inspect, text
    from app import main as main_module
    from app.config import settings

    stale_engine = create_engine(f"sqlite:///{tmp_path / 'stale_lessons.db'}")
    with stale_engine.begin() as connection:
        connection.execute(text("CREATE TABLE lesson_audio_recordings (id VARCHAR(36) PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE lesson_transcripts (id VARCHAR(36) PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE lesson_processing_jobs (id VARCHAR(36) PRIMARY KEY)"))

    monkeypatch.setattr(settings, "AUTO_CREATE_TABLES", True)
    monkeypatch.setattr(main_module, "engine", stale_engine)

    main_module.initialize_database()

    inspector = inspect(stale_engine)
    recording_columns = {column["name"] for column in inspector.get_columns("lesson_audio_recordings")}
    transcript_columns = {column["name"] for column in inspector.get_columns("lesson_transcripts")}
    job_columns = {column["name"] for column in inspector.get_columns("lesson_processing_jobs")}
    recording_indexes = {index["name"] for index in inspector.get_indexes("lesson_audio_recordings")}
    transcript_indexes = {index["name"] for index in inspector.get_indexes("lesson_transcripts")}

    assert {"duration_seconds", "sha256_checksum"}.issubset(recording_columns)
    assert {"edited_text", "review_status", "reviewed_at"}.issubset(transcript_columns)
    assert "document_types" in job_columns
    assert "ix_lesson_audio_recordings_sha256_checksum" in recording_indexes
    assert "ix_lesson_transcripts_review_status" in transcript_indexes


def test_alembic_baseline_creates_current_schema(monkeypatch, tmp_path):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect
    from app.config import settings

    db_path = tmp_path / "migration_baseline.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")

    repo_root = Path(__file__).resolve().parents[2]
    config = Config(str(repo_root / "backend" / "alembic.ini"))
    config.set_main_option("script_location", str(repo_root / "backend" / "alembic"))
    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{db_path}")
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    assert {
        "projects",
        "files",
        "compile_history",
        "project_snapshots",
        "generation_history",
        "generation_jobs",
        "pupils",
        "lessons",
        "lesson_audio_recordings",
        "lesson_transcripts",
        "lesson_generated_documents",
        "lesson_processing_jobs",
        "alembic_version",
    }.issubset(tables)
    assert "owner_id" in {column["name"] for column in inspector.get_columns("projects")}
    assert "ix_projects_owner_id" in {index["name"] for index in inspector.get_indexes("projects")}
    generation_history_indexes = {index["name"] for index in inspector.get_indexes("generation_history")}
    assert {"ix_generation_history_project_id", "ix_generation_history_owner_id"}.issubset(generation_history_indexes)
    assert "ix_pupils_teacher_id" in {index["name"] for index in inspector.get_indexes("pupils")}
    lesson_indexes = {index["name"] for index in inspector.get_indexes("lessons")}
    assert {"ix_lessons_teacher_id", "ix_lessons_pupil_id", "ix_lessons_lesson_date"}.issubset(lesson_indexes)
    lesson_columns = {column["name"] for column in inspector.get_columns("lessons")}
    assert {"pupil_id", "teacher_id", "topic", "lesson_date", "status"}.issubset(lesson_columns)
    recording_columns = {column["name"] for column in inspector.get_columns("lesson_audio_recordings")}
    assert {"lesson_id", "filename", "content_type", "size_bytes", "duration_seconds", "sha256_checksum", "storage_path", "status"}.issubset(recording_columns)
    recording_indexes = {index["name"] for index in inspector.get_indexes("lesson_audio_recordings")}
    assert {"ix_lesson_audio_recordings_lesson_id", "ix_lesson_audio_recordings_sha256_checksum"}.issubset(recording_indexes)
    transcript_columns = {column["name"] for column in inspector.get_columns("lesson_transcripts")}
    assert {"lesson_id", "recording_id", "provider", "language", "text", "edited_text", "review_status", "reviewed_at", "status", "error_message"}.issubset(transcript_columns)
    transcript_indexes = {index["name"] for index in inspector.get_indexes("lesson_transcripts")}
    assert {"ix_lesson_transcripts_lesson_id", "ix_lesson_transcripts_recording_id", "ix_lesson_transcripts_review_status"}.issubset(transcript_indexes)
    document_columns = {column["name"] for column in inspector.get_columns("lesson_generated_documents")}
    assert {
        "lesson_id",
        "transcript_id",
        "document_type",
        "title",
        "filename",
        "storage_path",
        "provider",
        "prompt_template_hash",
        "source_text_hash",
        "source_text_kind",
        "status",
    }.issubset(document_columns)
    document_indexes = {index["name"] for index in inspector.get_indexes("lesson_generated_documents")}
    assert {
        "ix_lesson_generated_documents_lesson_id",
        "ix_lesson_generated_documents_transcript_id",
        "ix_lesson_generated_documents_document_type",
    }.issubset(document_indexes)
    job_columns = {column["name"] for column in inspector.get_columns("lesson_processing_jobs")}
    assert {"lesson_id", "teacher_id", "job_type", "status", "stage", "recording_id", "transcript_id", "document_types", "document_ids", "error_message"}.issubset(job_columns)
    job_indexes = {index["name"] for index in inspector.get_indexes("lesson_processing_jobs")}
    assert {
        "ix_lesson_processing_jobs_lesson_id",
        "ix_lesson_processing_jobs_teacher_id",
        "ix_lesson_processing_jobs_job_type",
        "ix_lesson_processing_jobs_status",
    }.issubset(job_indexes)
    generation_history_columns = {column["name"] for column in inspector.get_columns("generation_history")}
    assert {"owner_id", "input_tokens", "output_tokens", "total_tokens", "token_count_source"}.issubset(generation_history_columns)
    generation_job_columns = {column["name"] for column in inspector.get_columns("generation_jobs")}
    assert {"project_id", "owner_id", "idempotency_key", "status", "stage", "request_hash", "prompt_hash", "request_payload", "result_payload", "error_message"}.issubset(generation_job_columns)
    generation_job_indexes = {index["name"] for index in inspector.get_indexes("generation_jobs")}
    assert {"ix_generation_jobs_project_id", "ix_generation_jobs_status", "ix_generation_jobs_request_hash", "ix_generation_jobs_owner_id", "ix_generation_jobs_idempotency_key"}.issubset(generation_job_indexes)


def test_health_check():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


def test_readiness_ready_when_all_checks_pass(monkeypatch):
    from app.schemas import ReadinessCheckResponse
    from app.services import readiness

    monkeypatch.setattr(
        readiness,
        "check_database_ready",
        lambda db_engine: ReadinessCheckResponse(status="ok", message="Database ok", details={"required_tables_present": True}),
    )
    monkeypatch.setattr(
        readiness,
        "check_compiler_ready",
        lambda: ReadinessCheckResponse(status="ok", message="Compiler ok", details={"binary": "pdflatex", "path": "/usr/bin/pdflatex"}),
    )
    monkeypatch.setattr(
        readiness,
        "check_latex_packages_ready",
        lambda compiler_check: ReadinessCheckResponse(status="ok", message="Packages ok", details={"russian_ldf": True, "t2aenc_def": True}),
    )
    monkeypatch.setattr(
        readiness,
        "check_artifact_dirs_ready",
        lambda: ReadinessCheckResponse(status="ok", message="Artifact dirs ok", details={"compile_work_dir": "ok", "upload_dir": "ok"}),
    )
    monkeypatch.setattr(
        readiness,
        "check_transcription_ready",
        lambda: ReadinessCheckResponse(status="skipped", message="Transcription disabled", details={"effective_provider": "disabled"}),
    )
    monkeypatch.setattr(
        readiness,
        "check_generation_jobs_ready",
        lambda: ReadinessCheckResponse(status="ok", message="Generation jobs ok", details={"counts": {}}),
    )
    monkeypatch.setattr(
        readiness,
        "check_ai_request_control_ready",
        lambda: ReadinessCheckResponse(status="ok", message="AI request control ok", details={"backend": "memory"}),
    )

    response = client.get("/api/ready")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert set(data["checks"]) == {"database", "compiler", "latex_packages", "artifact_dirs", "transcription", "generation_jobs", "ai_request_control"}
    assert data["checks"]["database"]["status"] == "ok"
    assert data["checks"]["compiler"]["status"] == "ok"


def test_readiness_degraded_when_pdflatex_is_missing(monkeypatch):
    from app.schemas import ReadinessCheckResponse
    from app.services import readiness

    monkeypatch.setattr(
        readiness,
        "check_database_ready",
        lambda db_engine: ReadinessCheckResponse(status="ok", message="Database ok", details={"required_tables_present": True}),
    )
    monkeypatch.setattr(
        readiness,
        "check_compiler_ready",
        lambda: ReadinessCheckResponse(status="missing", message="pdflatex was not found on PATH", details={"binary": "pdflatex", "path": None}),
    )
    monkeypatch.setattr(
        readiness,
        "check_latex_packages_ready",
        lambda compiler_check: ReadinessCheckResponse(status="skipped", message="Package checks skipped", details={"reason": compiler_check.status}),
    )
    monkeypatch.setattr(
        readiness,
        "check_artifact_dirs_ready",
        lambda: ReadinessCheckResponse(status="ok", message="Artifact dirs ok", details={"compile_work_dir": "ok", "upload_dir": "ok"}),
    )
    monkeypatch.setattr(
        readiness,
        "check_transcription_ready",
        lambda: ReadinessCheckResponse(status="skipped", message="Transcription disabled", details={"effective_provider": "disabled"}),
    )
    monkeypatch.setattr(
        readiness,
        "check_generation_jobs_ready",
        lambda: ReadinessCheckResponse(status="ok", message="Generation jobs ok", details={"counts": {}}),
    )
    monkeypatch.setattr(
        readiness,
        "check_ai_request_control_ready",
        lambda: ReadinessCheckResponse(status="ok", message="AI request control ok", details={"backend": "memory"}),
    )

    response = client.get("/api/ready")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "degraded"
    assert data["checks"]["compiler"]["status"] == "missing"
    assert data["checks"]["latex_packages"]["status"] == "skipped"
    assert data["checks"]["latex_packages"]["details"] == {"reason": "missing"}


def test_metrics_endpoint_returns_prometheus_text(monkeypatch):
    from app import main
    from app.schemas import ReadinessCheckResponse, ReadinessResponse

    readiness_response = ReadinessResponse(
        status="ready",
        checks={
            "database": ReadinessCheckResponse(status="ok", message="Database ok", details={}),
            "generation_jobs": ReadinessCheckResponse(
                status="ok",
                message="Generation jobs ok",
                details={"counts": {"queued": 1, "running": 0}, "backlog": 1, "stale_running": 0},
            ),
            "ai_request_control": ReadinessCheckResponse(status="ok", message="Memory", details={"backend": "memory"}),
        },
    )

    class FakeRequestControlService:
        def metrics_snapshot(self):
            return {
                "backend": "memory",
                "shared": False,
                "healthy": True,
                "rate_limit_decisions": {"allowed": 3, "limited": 1},
                "in_flight_decisions": {"accepted": 2, "duplicate": 1},
            }

    monkeypatch.setattr(main.readiness, "build_readiness_response", lambda db_engine: readiness_response)
    monkeypatch.setattr(main.generation, "request_control_service", FakeRequestControlService())

    response = client.get("/api/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert 'latexed_readiness_status{status="ready"} 1' in response.text
    assert 'latexed_generation_jobs_total{status="queued"} 1' in response.text
    assert 'latexed_ai_request_control_rate_limit_decisions_total{decision="limited"} 1' in response.text


def test_transcription_status_disabled_provider_is_skipped(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "TRANSCRIPTION_PROVIDER", "disabled")

    response = client.get("/api/transcription/status")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "skipped"
    assert data["details"]["configured_provider"] == "disabled"
    assert data["details"]["effective_provider"] == "disabled"


def test_transcription_status_reports_missing_faster_whisper_runtime(monkeypatch):
    from app.config import settings
    from app.services import transcription

    monkeypatch.setattr(settings, "TRANSCRIPTION_PROVIDER", "faster_whisper")
    monkeypatch.setattr(transcription.importlib.util, "find_spec", lambda module_name: None)
    monkeypatch.setattr(transcription.shutil, "which", lambda binary: None)

    response = client.get("/api/transcription/status")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "missing"
    assert data["details"]["dependency"] == {"module": "faster_whisper", "available": False}
    assert set(data["details"]["missing_requirements"]) == {"faster_whisper", "ffmpeg", "ffprobe"}
    assert data["details"]["install_hint"] == "uv sync --group transcription"


def test_readiness_degraded_when_enabled_transcription_runtime_is_missing(monkeypatch):
    from app.schemas import ReadinessCheckResponse
    from app.services import readiness

    monkeypatch.setattr(readiness, "check_database_ready", lambda db_engine: ReadinessCheckResponse(status="ok", message="Database ok", details={}))
    monkeypatch.setattr(readiness, "check_compiler_ready", lambda: ReadinessCheckResponse(status="ok", message="Compiler ok", details={}))
    monkeypatch.setattr(readiness, "check_latex_packages_ready", lambda compiler_check: ReadinessCheckResponse(status="ok", message="Packages ok", details={}))
    monkeypatch.setattr(readiness, "check_artifact_dirs_ready", lambda: ReadinessCheckResponse(status="ok", message="Artifact dirs ok", details={}))
    monkeypatch.setattr(
        readiness,
        "check_transcription_ready",
        lambda: ReadinessCheckResponse(status="missing", message="Transcription runtime missing", details={"missing_requirements": ["ffmpeg"]}),
    )
    monkeypatch.setattr(
        readiness,
        "check_generation_jobs_ready",
        lambda: ReadinessCheckResponse(status="ok", message="Generation jobs ok", details={"counts": {}}),
    )
    monkeypatch.setattr(
        readiness,
        "check_ai_request_control_ready",
        lambda: ReadinessCheckResponse(status="ok", message="AI request control ok", details={"backend": "memory"}),
    )

    response = client.get("/api/ready")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "degraded"
    assert data["checks"]["transcription"]["status"] == "missing"


def test_generation_job_readiness_reports_backlog_and_stale_running(monkeypatch):
    from datetime import timedelta
    from app.config import settings
    from app.routers import generation as generation_router
    from app.services import readiness
    from app.services.generation_job_worker import generation_job_service
    from app.time_utils import utc_now

    async def fake_generate(prompt, provider, model):
        return (
            "```latex\n"
            r"\section{Readiness}Queued"
            "\n```",
            "ollama",
            "qwen2.5:3b",
        )

    monkeypatch.setattr(settings, "AI_GENERATION_JOB_EXECUTION_MODE", "external")
    monkeypatch.setattr(settings, "AI_GENERATION_JOB_STALE_AFTER_SECONDS", 60)
    monkeypatch.setattr(generation_router.ai_generator, "generate", fake_generate)
    generation_router.rate_limit_buckets.clear()

    response = client.post(
        "/api/generation/jobs",
        json={"fields": {"topic": "Readiness"}, "materials": "Материал."},
    )
    assert response.status_code == 202
    job_id = response.json()["id"]

    db = SessionTesting()
    try:
        job = generation_job_service.get_job(db, job_id=job_id)
        stale_time = utc_now() - timedelta(seconds=300)
        job.status = "running"
        job.stage = "generating"
        job.updated_at = stale_time
        db.add(job)
        db.commit()
    finally:
        db.close()

    readiness_response = readiness.check_generation_jobs_ready(SessionTesting)

    assert readiness_response.status == "error"
    assert readiness_response.details["counts"]["running"] == 1
    assert readiness_response.details["stale_running"] == 1
    assert readiness_response.details["backlog"] == 1


def test_readiness_degraded_when_generation_jobs_are_stale(monkeypatch):
    from app.schemas import ReadinessCheckResponse
    from app.services import readiness

    monkeypatch.setattr(readiness, "check_database_ready", lambda db_engine: ReadinessCheckResponse(status="ok", message="Database ok", details={}))
    monkeypatch.setattr(readiness, "check_compiler_ready", lambda: ReadinessCheckResponse(status="ok", message="Compiler ok", details={}))
    monkeypatch.setattr(readiness, "check_latex_packages_ready", lambda compiler_check: ReadinessCheckResponse(status="ok", message="Packages ok", details={}))
    monkeypatch.setattr(readiness, "check_artifact_dirs_ready", lambda: ReadinessCheckResponse(status="ok", message="Artifact dirs ok", details={}))
    monkeypatch.setattr(readiness, "check_transcription_ready", lambda: ReadinessCheckResponse(status="skipped", message="Transcription disabled", details={}))
    monkeypatch.setattr(
        readiness,
        "check_generation_jobs_ready",
        lambda: ReadinessCheckResponse(status="error", message="Generation worker has stale running jobs", details={"stale_running": 1}),
    )
    monkeypatch.setattr(
        readiness,
        "check_ai_request_control_ready",
        lambda: ReadinessCheckResponse(status="ok", message="AI request control ok", details={"backend": "memory"}),
    )

    response = client.get("/api/ready")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "degraded"
    assert data["checks"]["generation_jobs"]["status"] == "error"


def test_readiness_degraded_when_ai_request_control_is_unavailable(monkeypatch):
    from app.schemas import ReadinessCheckResponse
    from app.services import readiness

    monkeypatch.setattr(readiness, "check_database_ready", lambda db_engine: ReadinessCheckResponse(status="ok", message="Database ok", details={}))
    monkeypatch.setattr(readiness, "check_compiler_ready", lambda: ReadinessCheckResponse(status="ok", message="Compiler ok", details={}))
    monkeypatch.setattr(readiness, "check_latex_packages_ready", lambda compiler_check: ReadinessCheckResponse(status="ok", message="Packages ok", details={}))
    monkeypatch.setattr(readiness, "check_artifact_dirs_ready", lambda: ReadinessCheckResponse(status="ok", message="Artifact dirs ok", details={}))
    monkeypatch.setattr(readiness, "check_transcription_ready", lambda: ReadinessCheckResponse(status="skipped", message="Transcription disabled", details={}))
    monkeypatch.setattr(readiness, "check_generation_jobs_ready", lambda: ReadinessCheckResponse(status="ok", message="Generation jobs ok", details={}))
    monkeypatch.setattr(
        readiness,
        "check_ai_request_control_ready",
        lambda: ReadinessCheckResponse(status="error", message="AI request control unavailable", details={"backend": "redis"}),
    )

    response = client.get("/api/ready")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "degraded"
    assert data["checks"]["ai_request_control"]["status"] == "error"


def test_root():
    response = client.get("/")
    assert response.status_code == 200


def test_request_logging_adds_request_id_header():
    response = client.get("/api/health", headers={"X-Request-ID": "test-request-id"})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "test-request-id"
    assert "X-Process-Time" in response.headers


def test_cors_preflight_allows_local_development_origins():
    response = client.options(
        "/api/health",
        headers={
            "Origin": "http://127.0.0.1:8080",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:8080"


def test_create_project():
    response = client.post(
        "/api/projects/",
        json={"name": "Test Project"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Project"
    assert "id" in data


def test_list_projects():
    # Create a project first
    client.post("/api/projects/", json={"name": "Test Project 1"})
    client.post("/api/projects/", json={"name": "Test Project 2"})

    response = client.get("/api/projects/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2


def test_get_project():
    create_response = client.post("/api/projects/", json={"name": "Test Project"})
    project_id = create_response.json()["id"]

    response = client.get(f"/api/projects/{project_id}")
    assert response.status_code == 200
    assert response.json()["name"] == "Test Project"


def test_update_project():
    create_response = client.post("/api/projects/", json={"name": "Old Name"})
    project_id = create_response.json()["id"]

    response = client.put(
        f"/api/projects/{project_id}",
        json={"name": "New Name"},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "New Name"


def test_delete_project():
    create_response = client.post("/api/projects/", json={"name": "To Delete"})
    project_id = create_response.json()["id"]

    response = client.delete(f"/api/projects/{project_id}")
    assert response.status_code == 200

    # Verify deletion
    response = client.get(f"/api/projects/{project_id}")
    assert response.status_code == 404


def test_project_ownership_uses_trusted_user_header(monkeypatch):
    enable_trusted_proxy_auth(monkeypatch)
    owner_headers = {"X-Latexed-User": "teacher-a"}
    other_headers = {"X-Latexed-User": "teacher-b"}
    create_response = client.post("/api/projects/", json={"name": "Scoped Project"}, headers=owner_headers)
    assert create_response.status_code == 201
    project = create_response.json()

    assert project["owner_id"] == "teacher-a"
    assert client.get("/api/projects/", headers=owner_headers).json()[0]["id"] == project["id"]
    assert client.get("/api/projects/", headers=other_headers).json() == []
    assert client.get(f"/api/projects/{project['id']}", headers=other_headers).status_code == 404


def test_blank_trusted_user_header_is_rejected(monkeypatch):
    enable_trusted_proxy_auth(monkeypatch)
    response = client.get("/api/projects/", headers={"X-Latexed-User": "   "})

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid user identity"


def test_local_auth_mode_ignores_spoofed_trusted_user_header(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "AUTH_MODE", "local")
    monkeypatch.setattr(settings, "LOCAL_USER_ID", "local-teacher")

    response = client.post(
        "/api/projects/",
        json={"name": "Local Auth Project"},
        headers={"X-Latexed-User": "attacker"},
    )

    assert response.status_code == 201
    assert response.json()["owner_id"] == "local-teacher"


def test_trusted_proxy_auth_requires_identity_header(monkeypatch):
    enable_trusted_proxy_auth(monkeypatch)

    response = client.get("/api/projects/")

    assert response.status_code == 401
    assert response.json()["detail"] == "Trusted proxy identity header is required"


def test_trusted_proxy_auth_rejects_untrusted_client(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "AUTH_MODE", "trusted_proxy")
    monkeypatch.setattr(settings, "TRUSTED_PROXY_IPS", ["192.0.2.10"])

    response = client.get("/api/projects/", headers={"X-Latexed-User": "teacher-a"})

    assert response.status_code == 403
    assert response.json()["detail"] == "Trusted proxy identity is not allowed from this client"


def test_security_config_rejects_unsafe_production_defaults(monkeypatch):
    from app.config import settings
    from app.services.security_config import SecurityConfigurationError, validate_security_settings

    monkeypatch.setattr(settings, "DEPLOYMENT_ENV", "production")
    monkeypatch.setattr(settings, "AUTH_MODE", "local")
    monkeypatch.setattr(settings, "ALLOW_PRODUCTION_LOCAL_AUTH", True)
    monkeypatch.setattr(settings, "ALLOWED_HOSTS", ["latexed.example.com"])
    monkeypatch.setattr(settings, "SECRET_KEY", "change-me-in-production-please")

    with pytest.raises(SecurityConfigurationError, match="SECRET_KEY"):
        validate_security_settings()


def test_security_config_rejects_wildcard_production_hosts(monkeypatch):
    from app.config import settings
    from app.services.security_config import SecurityConfigurationError, validate_security_settings

    monkeypatch.setattr(settings, "DEPLOYMENT_ENV", "production")
    monkeypatch.setattr(settings, "AUTH_MODE", "local")
    monkeypatch.setattr(settings, "ALLOW_PRODUCTION_LOCAL_AUTH", True)
    monkeypatch.setattr(settings, "SECRET_KEY", "not-default")
    monkeypatch.setattr(settings, "ALLOWED_HOSTS", ["*"])

    with pytest.raises(SecurityConfigurationError, match="ALLOWED_HOSTS"):
        validate_security_settings()


def test_security_config_requires_trusted_proxy_ips(monkeypatch):
    from app.config import settings
    from app.services.security_config import SecurityConfigurationError, validate_security_settings

    monkeypatch.setattr(settings, "DEPLOYMENT_ENV", "development")
    monkeypatch.setattr(settings, "AUTH_MODE", "trusted_proxy")
    monkeypatch.setattr(settings, "TRUSTED_PROXY_IPS", [])

    with pytest.raises(SecurityConfigurationError, match="TRUSTED_PROXY_IPS"):
        validate_security_settings()


def test_security_config_accepts_hardened_trusted_proxy_production(monkeypatch):
    from app.config import settings
    from app.services.security_config import validate_security_settings

    monkeypatch.setattr(settings, "DEPLOYMENT_ENV", "production")
    monkeypatch.setattr(settings, "AUTH_MODE", "trusted_proxy")
    monkeypatch.setattr(settings, "TRUSTED_PROXY_IPS", ["172.20.0.0/16"])
    monkeypatch.setattr(settings, "TRUSTED_USER_HEADER", "X-Latexed-User")
    monkeypatch.setattr(settings, "SECRET_KEY", "not-default")
    monkeypatch.setattr(settings, "ALLOWED_HOSTS", ["latexed.example.com"])

    validate_security_settings()


def test_nginx_drops_trusted_user_header_by_default():
    nginx_conf = (Path(__file__).resolve().parents[1] / "nginx" / "nginx.conf").read_text(encoding="utf-8")

    assert 'proxy_set_header X-Latexed-User "";' in nginx_conf
    assert "$http_x_latexed_user" not in nginx_conf


def test_production_compose_declares_security_env():
    compose = (Path(__file__).resolve().parents[1] / "docker-compose.prod.yml").read_text(encoding="utf-8")

    for expected in [
        "DEPLOYMENT_ENV=production",
        "AUTH_MODE=${AUTH_MODE:-trusted_proxy}",
        "TRUSTED_PROXY_IPS=${TRUSTED_PROXY_IPS}",
        "ALLOWED_HOSTS=${ALLOWED_HOSTS}",
        "ALLOW_PRODUCTION_LOCAL_AUTH=${ALLOW_PRODUCTION_LOCAL_AUTH:-false}",
    ]:
        assert expected in compose


def create_test_pupil(display_name: str = "Николь") -> dict:
    response = client.post("/api/pupils/", json={"display_name": display_name, "notes": "ЕГЭ"})
    assert response.status_code == 201
    return response.json()


def create_test_lesson(pupil_id: str, topic: str = "Показательные уравнения", lesson_date: str = "2026-06-09T10:00:00Z") -> dict:
    response = client.post(
        "/api/lessons/",
        json={"pupil_id": pupil_id, "topic": topic, "lesson_date": lesson_date},
    )
    assert response.status_code == 201
    return response.json()


def test_create_pupil():
    response = client.post("/api/pupils/", json={"display_name": "Николь", "notes": "ЕГЭ"})

    assert response.status_code == 201
    data = response.json()
    assert data["display_name"] == "Николь"
    assert data["notes"] == "ЕГЭ"
    assert data["teacher_id"] == "local-teacher"
    assert "id" in data


def test_pupil_crud():
    pupil = create_test_pupil("Анна")

    list_response = client.get("/api/pupils/")
    assert list_response.status_code == 200
    assert [item["display_name"] for item in list_response.json()] == ["Анна"]

    get_response = client.get(f"/api/pupils/{pupil['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["display_name"] == "Анна"

    update_response = client.patch(f"/api/pupils/{pupil['id']}", json={"display_name": "Анна П."})
    assert update_response.status_code == 200
    assert update_response.json()["display_name"] == "Анна П."

    delete_response = client.delete(f"/api/pupils/{pupil['id']}")
    assert delete_response.status_code == 200
    assert client.get(f"/api/pupils/{pupil['id']}").status_code == 404


def test_create_lesson_for_pupil():
    pupil = create_test_pupil()

    lesson = create_test_lesson(pupil["id"])

    assert lesson["pupil_id"] == pupil["id"]
    assert lesson["teacher_id"] == "local-teacher"
    assert lesson["topic"] == "Показательные уравнения"
    assert lesson["status"] == "draft"
    assert lesson["lesson_date"].startswith("2026-06-09T10:00:00")


def test_create_lesson_rejects_unknown_pupil():
    response = client.post(
        "/api/lessons/",
        json={"pupil_id": "missing", "topic": "Тригонометрия"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Pupil not found"


def test_lesson_crud_and_filters():
    pupil = create_test_pupil("Михаил")
    other_pupil = create_test_pupil("Софья")
    lesson = create_test_lesson(pupil["id"], topic="Логарифмы", lesson_date="2026-06-09T10:00:00Z")
    create_test_lesson(other_pupil["id"], topic="Производная", lesson_date="2026-06-10T10:00:00Z")

    list_response = client.get(f"/api/lessons/?pupil_id={pupil['id']}")
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == [lesson["id"]]

    date_response = client.get("/api/lessons/?date_from=2026-06-09T00:00:00Z&date_to=2026-06-09T23:59:59Z")
    assert date_response.status_code == 200
    assert [item["topic"] for item in date_response.json()] == ["Логарифмы"]

    get_response = client.get(f"/api/lessons/{lesson['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["topic"] == "Логарифмы"

    update_response = client.patch(f"/api/lessons/{lesson['id']}", json={"topic": "Логарифмы и степени", "status": "completed"})
    assert update_response.status_code == 200
    assert update_response.json()["topic"] == "Логарифмы и степени"
    assert update_response.json()["status"] == "completed"

    delete_response = client.delete(f"/api/lessons/{lesson['id']}")
    assert delete_response.status_code == 200
    assert client.get(f"/api/lessons/{lesson['id']}").status_code == 404


def test_lesson_teacher_scope_placeholder(monkeypatch):
    from app.dependencies import get_current_teacher_id

    pupil = create_test_pupil("Scoped Student")
    lesson = create_test_lesson(pupil["id"], topic="Стереометрия")

    app.dependency_overrides[get_current_teacher_id] = lambda: "other-teacher"
    try:
        assert client.get("/api/pupils/").json() == []
        assert client.get("/api/lessons/").json() == []
        assert client.get(f"/api/pupils/{pupil['id']}").status_code == 404
        assert client.get(f"/api/lessons/{lesson['id']}").status_code == 404
        cross_scope_response = client.post(
            "/api/lessons/",
            json={"pupil_id": pupil["id"], "topic": "Недоступное занятие"},
        )
        assert cross_scope_response.status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_teacher_id, None)


def upload_test_recording(
    lesson_id: str,
    *,
    filename: str = "recording.webm",
    content_type: str = "audio/webm",
    data: bytes = b"audio",
):
    return client.post(
        f"/api/lessons/{lesson_id}/recordings",
        files={"file": (filename, data, content_type)},
    )


def test_lesson_audio_upload_success(monkeypatch, tmp_path):
    from app.config import settings

    monkeypatch.setattr(settings, "LESSON_ARTIFACT_ROOT", str(tmp_path / "lesson_artifacts"))
    pupil = create_test_pupil("Audio Student")
    lesson = create_test_lesson(pupil["id"], lesson_date="2026-06-09T10:00:00Z")

    response = upload_test_recording(lesson["id"], data=b"webm-data")

    assert response.status_code == 201
    data = response.json()
    assert data["lesson_id"] == lesson["id"]
    assert data["filename"] == "recording.webm"
    assert data["content_type"] == "audio/webm"
    assert data["size_bytes"] == len(b"webm-data")
    assert data["sha256_checksum"] == hashlib.sha256(b"webm-data").hexdigest()
    assert data["status"] == "uploaded"

    stored_files = list((tmp_path / "lesson_artifacts").rglob("*.webm"))
    assert len(stored_files) == 1
    assert stored_files[0].read_bytes() == b"webm-data"
    assert "recording.webm" not in str(stored_files[0].relative_to(tmp_path / "lesson_artifacts"))

    lesson_response = client.get(f"/api/lessons/{lesson['id']}")
    assert lesson_response.status_code == 200
    assert lesson_response.json()["status"] == "recording_uploaded"


def test_lesson_audio_upload_persists_probed_duration(monkeypatch, tmp_path):
    from app.config import settings
    from app.services import audio_storage

    monkeypatch.setattr(settings, "LESSON_ARTIFACT_ROOT", str(tmp_path / "lesson_artifacts"))
    monkeypatch.setattr(audio_storage, "probe_audio_duration_seconds", lambda path: 42.5)
    pupil = create_test_pupil("Duration Audio Student")
    lesson = create_test_lesson(pupil["id"])

    response = upload_test_recording(lesson["id"], data=b"duration-webm")

    assert response.status_code == 201
    data = response.json()
    assert data["duration_seconds"] == 42.5
    assert data["sha256_checksum"] == hashlib.sha256(b"duration-webm").hexdigest()


def test_lesson_audio_upload_rejects_duration_over_limit(monkeypatch, tmp_path):
    from app.config import settings
    from app.services import audio_storage

    monkeypatch.setattr(settings, "LESSON_ARTIFACT_ROOT", str(tmp_path / "lesson_artifacts"))
    monkeypatch.setattr(settings, "MAX_LESSON_AUDIO_DURATION_SECONDS", 60)
    monkeypatch.setattr(audio_storage, "probe_audio_duration_seconds", lambda path: 61.0)
    pupil = create_test_pupil("Too Long Audio Student")
    lesson = create_test_lesson(pupil["id"])

    response = upload_test_recording(lesson["id"], data=b"too-long-webm")

    assert response.status_code == 413
    assert response.json()["detail"] == "Audio duration exceeds configured limit"
    assert not list((tmp_path / "lesson_artifacts").rglob("*.webm"))


def test_lesson_audio_upload_rejects_path_traversal_filename(monkeypatch, tmp_path):
    from app.config import settings

    monkeypatch.setattr(settings, "LESSON_ARTIFACT_ROOT", str(tmp_path / "lesson_artifacts"))
    pupil = create_test_pupil("Unsafe Audio Student")
    lesson = create_test_lesson(pupil["id"])

    response = upload_test_recording(lesson["id"], filename="../recording.webm")

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid audio filename"
    assert not (tmp_path / "lesson_artifacts").exists()


def test_lesson_audio_upload_rejects_unsupported_content_type(monkeypatch, tmp_path):
    from app.config import settings

    monkeypatch.setattr(settings, "LESSON_ARTIFACT_ROOT", str(tmp_path / "lesson_artifacts"))
    pupil = create_test_pupil("Unsupported Audio Student")
    lesson = create_test_lesson(pupil["id"])

    response = upload_test_recording(lesson["id"], filename="recording.txt", content_type="text/plain")

    assert response.status_code == 415
    assert response.json()["detail"] in {"Unsupported audio file extension", "Unsupported audio content type"}
    assert not (tmp_path / "lesson_artifacts").exists()


def test_lesson_audio_upload_rejects_oversized_payload(monkeypatch, tmp_path):
    from app.config import settings

    monkeypatch.setattr(settings, "LESSON_ARTIFACT_ROOT", str(tmp_path / "lesson_artifacts"))
    monkeypatch.setattr(settings, "MAX_LESSON_AUDIO_SIZE", 4)
    pupil = create_test_pupil("Oversized Audio Student")
    lesson = create_test_lesson(pupil["id"])

    response = upload_test_recording(lesson["id"], data=b"12345")

    assert response.status_code == 413
    assert response.json()["detail"] == "Audio payload exceeds configured size limit"
    assert not (tmp_path / "lesson_artifacts").exists()


def test_lesson_audio_upload_respects_teacher_scope(monkeypatch, tmp_path):
    from app.config import settings
    from app.dependencies import get_current_teacher_id

    monkeypatch.setattr(settings, "LESSON_ARTIFACT_ROOT", str(tmp_path / "lesson_artifacts"))
    pupil = create_test_pupil("Scoped Audio Student")
    lesson = create_test_lesson(pupil["id"])

    app.dependency_overrides[get_current_teacher_id] = lambda: "other-teacher"
    try:
        response = upload_test_recording(lesson["id"])
        assert response.status_code == 404
        assert response.json()["detail"] == "Lesson not found"
        assert not (tmp_path / "lesson_artifacts").exists()
    finally:
        app.dependency_overrides.pop(get_current_teacher_id, None)


def test_lesson_audio_upload_rejects_unknown_lesson(monkeypatch, tmp_path):
    from app.config import settings

    monkeypatch.setattr(settings, "LESSON_ARTIFACT_ROOT", str(tmp_path / "lesson_artifacts"))

    response = upload_test_recording("missing-lesson")

    assert response.status_code == 404
    assert response.json()["detail"] == "Lesson not found"



def test_legacy_transcription_loader_uses_root_transcribe_script(monkeypatch):
    import shutil
    import sys
    from types import SimpleNamespace

    from app.services.transcription import load_legacy_transcibe_module

    repo_root = Path(__file__).resolve().parents[2]
    test_audio = repo_root / "test_audio.mp3"
    assert test_audio.exists()

    monkeypatch.setitem(sys.modules, "whisper", SimpleNamespace(load_model=lambda model_name: object()))

    module = load_legacy_transcibe_module()

    assert module.__file__ == str(repo_root / "transcribe.py")
    assert module.AUDIO_EXTENSIONS >= {".mp3"}
    if shutil.which("ffprobe") is None:
        pytest.skip("ffprobe is required to probe repository test_audio.mp3")
    assert module.get_audio_duration_seconds(test_audio) > 0

def test_lesson_transcription_success_with_fake_provider(monkeypatch, tmp_path):
    from app.config import settings
    from app.routers import lessons as lessons_router
    from app.services.transcription import FakeTranscriptionProvider, TranscriptionService

    monkeypatch.setattr(settings, "LESSON_ARTIFACT_ROOT", str(tmp_path / "lesson_artifacts"))
    monkeypatch.setattr(
        lessons_router,
        "transcription_service",
        TranscriptionService(provider=FakeTranscriptionProvider(text="Ученик решил квадратное уравнение")),
    )
    pupil = create_test_pupil("Transcript Student")
    lesson = create_test_lesson(pupil["id"])
    recording = upload_test_recording(lesson["id"], data=b"webm-data").json()

    response = client.post(
        f"/api/lessons/{lesson['id']}/transcribe",
        json={"recording_id": recording["id"], "language": "ru"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["lesson_id"] == lesson["id"]
    assert data["recording_id"] == recording["id"]
    assert data["provider"] == "fake"
    assert data["language"] == "ru"
    assert data["text"] == "Ученик решил квадратное уравнение"
    assert data["status"] == "completed"
    assert data["error_message"] is None

    lesson_response = client.get(f"/api/lessons/{lesson['id']}")
    assert lesson_response.status_code == 200
    assert lesson_response.json()["status"] == "transcript_ready"


def test_lesson_transcript_review_list_get_and_update(monkeypatch, tmp_path):
    lesson, transcript = create_transcribed_lesson(
        monkeypatch,
        tmp_path,
        transcript_text="сырой текст распознавания",
    )

    list_response = client.get(f"/api/lessons/{lesson['id']}/transcripts")
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == [transcript["id"]]
    assert list_response.json()[0]["review_status"] == "unreviewed"

    get_response = client.get(f"/api/lessons/{lesson['id']}/transcripts/{transcript['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["text"] == "сырой текст распознавания"

    update_response = client.patch(
        f"/api/lessons/{lesson['id']}/transcripts/{transcript['id']}",
        json={"edited_text": "исправленный текст для документов", "review_status": "reviewed"},
    )

    assert update_response.status_code == 200
    data = update_response.json()
    assert data["text"] == "сырой текст распознавания"
    assert data["edited_text"] == "исправленный текст для документов"
    assert data["review_status"] == "reviewed"
    assert data["reviewed_at"] is not None


def test_lesson_transcript_review_rejects_failed_transcript(monkeypatch, tmp_path):
    from app.config import settings
    from app.routers import lessons as lessons_router
    from app.services.transcription import FakeTranscriptionProvider, TranscriptionService

    monkeypatch.setattr(settings, "LESSON_ARTIFACT_ROOT", str(tmp_path / "lesson_artifacts"))
    monkeypatch.setattr(
        lessons_router,
        "transcription_service",
        TranscriptionService(provider=FakeTranscriptionProvider(fail=True)),
    )
    pupil = create_test_pupil("Failed Review Student")
    lesson = create_test_lesson(pupil["id"])
    upload_test_recording(lesson["id"], data=b"webm-data")
    transcript = client.post(f"/api/lessons/{lesson['id']}/transcribe", json={}).json()

    response = client.patch(
        f"/api/lessons/{lesson['id']}/transcripts/{transcript['id']}",
        json={"edited_text": "нельзя ревьюить", "review_status": "reviewed"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Only completed transcripts can be reviewed"


def test_transcription_provider_registry_selects_faster_whisper(monkeypatch):
    from app.config import settings
    from app.services.transcription import (
        DisabledTranscriptionProvider,
        FasterWhisperTranscriptionProvider,
        available_transcription_providers,
        build_transcription_provider,
    )

    monkeypatch.setattr(settings, "TRANSCRIPTION_PROVIDER", "faster_whisper")
    monkeypatch.setattr(settings, "TRANSCRIPTION_MODEL", "small")
    monkeypatch.setattr(settings, "TRANSCRIPTION_DEVICE", "cpu")
    monkeypatch.setattr(settings, "TRANSCRIPTION_COMPUTE_TYPE", "int8")
    monkeypatch.setattr(settings, "TRANSCRIPTION_BEAM_SIZE", 3)
    monkeypatch.setattr(settings, "TRANSCRIPTION_WORD_TIMESTAMPS", True)

    provider = build_transcription_provider()

    assert "faster_whisper" in available_transcription_providers()
    assert isinstance(provider, FasterWhisperTranscriptionProvider)
    assert provider.model_name == "small"
    assert provider.device == "cpu"
    assert provider.compute_type == "int8"
    assert provider.beam_size == 3
    assert provider.word_timestamps is True

    monkeypatch.setattr(settings, "TRANSCRIPTION_PROVIDER", "unknown-provider")
    assert isinstance(build_transcription_provider(), DisabledTranscriptionProvider)


def test_faster_whisper_provider_maps_segments(monkeypatch, tmp_path):
    import sys
    from types import SimpleNamespace
    from app.services.transcription import FasterWhisperTranscriptionProvider

    captured = {}

    class FakeWhisperModel:
        def __init__(self, model_name, *, device, compute_type):
            captured["model_name"] = model_name
            captured["device"] = device
            captured["compute_type"] = compute_type

        def transcribe(self, audio_path, *, language, beam_size, word_timestamps):
            captured["audio_path"] = audio_path
            captured["language"] = language
            captured["beam_size"] = beam_size
            captured["word_timestamps"] = word_timestamps
            return (
                [
                    SimpleNamespace(start=0.0, end=1.25, text=" Первый фрагмент "),
                    SimpleNamespace(start=1.25, end=2.5, text="Второй фрагмент"),
                ],
                SimpleNamespace(language="ru", duration=2.5),
            )

    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=FakeWhisperModel))
    audio_path = tmp_path / "recording.webm"
    audio_path.write_bytes(b"audio")
    provider = FasterWhisperTranscriptionProvider(
        model_name="base",
        device="cpu",
        compute_type="int8",
        beam_size=5,
        word_timestamps=False,
    )

    result = provider.transcribe(audio_path, language="ru")

    assert captured == {
        "model_name": "base",
        "device": "cpu",
        "compute_type": "int8",
        "audio_path": str(audio_path),
        "language": "ru",
        "beam_size": 5,
        "word_timestamps": False,
    }
    assert result.provider == "faster_whisper"
    assert result.language == "ru"
    assert result.duration_seconds == 2.5
    assert result.text == "Первый фрагмент\nВторой фрагмент"
    assert [(segment.start, segment.end, segment.text) for segment in result.segments] == [
        (0.0, 1.25, "Первый фрагмент"),
        (1.25, 2.5, "Второй фрагмент"),
    ]



def test_lesson_transcription_disabled_provider_logs_actionable_warning(monkeypatch, tmp_path, caplog):
    import logging

    from app.config import settings
    from app.routers import lessons as lessons_router
    from app.services.transcription import DisabledTranscriptionProvider, TranscriptionService

    monkeypatch.setattr(settings, "LESSON_ARTIFACT_ROOT", str(tmp_path / "lesson_artifacts"))
    monkeypatch.setattr(
        lessons_router,
        "transcription_service",
        TranscriptionService(provider=DisabledTranscriptionProvider()),
    )
    caplog.set_level(logging.INFO, logger="app.services.transcription")
    pupil = create_test_pupil("Disabled Provider Student")
    lesson = create_test_lesson(pupil["id"])
    upload_test_recording(lesson["id"], filename="recording.mp3", content_type="audio/mpeg", data=b"mp3-data")

    response = client.post(f"/api/lessons/{lesson['id']}/transcribe", json={})

    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "failed"
    assert "Set TRANSCRIPTION_PROVIDER" in data["error_message"]
    assert any("lesson transcription provider unavailable" in record.message for record in caplog.records)
    assert not any(record.levelno >= logging.ERROR for record in caplog.records)

def test_lesson_transcription_provider_failure_creates_failed_transcript(monkeypatch, tmp_path):
    from app.config import settings
    from app.routers import lessons as lessons_router
    from app.services.transcription import FakeTranscriptionProvider, TranscriptionService

    monkeypatch.setattr(settings, "LESSON_ARTIFACT_ROOT", str(tmp_path / "lesson_artifacts"))
    monkeypatch.setattr(
        lessons_router,
        "transcription_service",
        TranscriptionService(provider=FakeTranscriptionProvider(fail=True)),
    )
    pupil = create_test_pupil("Failed Transcript Student")
    lesson = create_test_lesson(pupil["id"])
    upload_test_recording(lesson["id"], data=b"webm-data")

    response = client.post(f"/api/lessons/{lesson['id']}/transcribe", json={})

    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "failed"
    assert data["text"] is None
    assert data["error_message"] == "Fake transcription provider failed"

    lesson_response = client.get(f"/api/lessons/{lesson['id']}")
    assert lesson_response.status_code == 200
    assert lesson_response.json()["status"] == "recording_uploaded"


def test_lesson_transcription_rejects_lesson_without_recording(monkeypatch):
    from app.routers import lessons as lessons_router
    from app.services.transcription import FakeTranscriptionProvider, TranscriptionService

    monkeypatch.setattr(
        lessons_router,
        "transcription_service",
        TranscriptionService(provider=FakeTranscriptionProvider()),
    )
    pupil = create_test_pupil("No Recording Transcript Student")
    lesson = create_test_lesson(pupil["id"])

    response = client.post(f"/api/lessons/{lesson['id']}/transcribe", json={})

    assert response.status_code == 404
    assert response.json()["detail"] == "Recording not found"


def test_lesson_transcription_respects_teacher_scope(monkeypatch, tmp_path):
    from app.config import settings
    from app.dependencies import get_current_teacher_id
    from app.routers import lessons as lessons_router
    from app.services.transcription import FakeTranscriptionProvider, TranscriptionService

    monkeypatch.setattr(settings, "LESSON_ARTIFACT_ROOT", str(tmp_path / "lesson_artifacts"))
    monkeypatch.setattr(
        lessons_router,
        "transcription_service",
        TranscriptionService(provider=FakeTranscriptionProvider()),
    )
    pupil = create_test_pupil("Scoped Transcript Student")
    lesson = create_test_lesson(pupil["id"])
    upload_test_recording(lesson["id"], data=b"webm-data")

    app.dependency_overrides[get_current_teacher_id] = lambda: "other-teacher"
    try:
        response = client.post(f"/api/lessons/{lesson['id']}/transcribe", json={})
        assert response.status_code == 404
        assert response.json()["detail"] == "Lesson not found"
    finally:
        app.dependency_overrides.pop(get_current_teacher_id, None)


def create_transcribed_lesson(monkeypatch, tmp_path, *, topic: str = "Quadratic & roots_1", transcript_text: str = "x_1 & 50% done"):
    from app.config import settings
    from app.routers import lessons as lessons_router
    from app.services.transcription import FakeTranscriptionProvider, TranscriptionService

    monkeypatch.setattr(settings, "LESSON_ARTIFACT_ROOT", str(tmp_path / "lesson_artifacts"))
    monkeypatch.setattr(
        lessons_router,
        "transcription_service",
        TranscriptionService(provider=FakeTranscriptionProvider(text=transcript_text)),
    )
    pupil = create_test_pupil("Document Student")
    lesson = create_test_lesson(pupil["id"], topic=topic)
    recording = upload_test_recording(lesson["id"], data=b"webm-data").json()
    transcript_response = client.post(
        f"/api/lessons/{lesson['id']}/transcribe",
        json={"recording_id": recording["id"], "language": "ru"},
    )
    assert transcript_response.status_code == 201
    return lesson, transcript_response.json()


def test_lesson_prompt_templates_are_parameterized():
    from app.services.lesson_documents import LessonPromptService

    prompt_service = LessonPromptService()

    check_list = prompt_service.load("check_list")
    mistakes = prompt_service.load("pupil_mistakes")

    assert "Николь" not in check_list
    assert "Николь" not in mistakes
    assert "{{ pupil_display_name }}" in check_list
    assert "{{ transcript_text }}" in check_list


def test_lesson_document_generation_success_and_download(monkeypatch, tmp_path):
    lesson, transcript = create_transcribed_lesson(monkeypatch, tmp_path)

    response = client.post(f"/api/lessons/{lesson['id']}/documents/generate", json={})

    assert response.status_code == 409
    assert response.json()["detail"] == "Review the transcript or set allow_unreviewed=true to create draft lesson documents"

    response = client.post(f"/api/lessons/{lesson['id']}/documents/generate", json={"allow_unreviewed": True})

    assert response.status_code == 201
    documents = response.json()
    assert {document["document_type"] for document in documents} == {"check_list", "pupil_mistakes"}
    assert all(document["status"] == "draft" for document in documents)
    assert all(document["provider"] == "fake" for document in documents)
    assert all(document["source_text_kind"] == "raw" for document in documents)
    assert all(len(document["source_text_hash"]) == 64 for document in documents)
    assert all(len(document["prompt_template_hash"]) == 64 for document in documents)
    assert all(document["transcript_id"] == transcript["id"] for document in documents)
    assert all(document["download_url"].endswith(f"/documents/{document['id']}/download") for document in documents)
    assert all("/" not in document["filename"] and ".." not in document["filename"] for document in documents)

    stored_files = list((tmp_path / "lesson_artifacts").rglob("*.tex"))
    assert len(stored_files) == 2
    combined_latex = "\n".join(path.read_text(encoding="utf-8") for path in stored_files)
    assert r"Quadratic \& roots\_1" in combined_latex
    assert r"x\_1 \& 50\% done" in combined_latex

    list_response = client.get(f"/api/lessons/{lesson['id']}/documents")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 2

    download_response = client.get(documents[0]["download_url"])
    assert download_response.status_code == 200
    assert r"\documentclass" in download_response.text
    assert documents[0]["filename"] in download_response.headers["content-disposition"]

    lesson_response = client.get(f"/api/lessons/{lesson['id']}")
    assert lesson_response.status_code == 200
    assert lesson_response.json()["status"] == "transcript_ready"


def test_lesson_document_generation_uses_reviewed_transcript_text(monkeypatch, tmp_path):
    lesson, transcript = create_transcribed_lesson(monkeypatch, tmp_path, transcript_text="сырой x_1")
    update_response = client.patch(
        f"/api/lessons/{lesson['id']}/transcripts/{transcript['id']}",
        json={"edited_text": "исправленный y_2", "review_status": "reviewed"},
    )
    assert update_response.status_code == 200

    response = client.post(f"/api/lessons/{lesson['id']}/documents/generate", json={"transcript_id": transcript["id"]})

    assert response.status_code == 201
    documents = response.json()
    assert all(document["status"] == "completed" for document in documents)
    assert all(document["source_text_kind"] == "edited" for document in documents)
    stored_files = list((tmp_path / "lesson_artifacts").rglob("*.tex"))
    combined_latex = "\n".join(path.read_text(encoding="utf-8") for path in stored_files)
    assert r"исправленный y\_2" in combined_latex
    assert r"сырой x\_1" not in combined_latex


def test_lesson_document_generation_requires_completed_transcript(monkeypatch, tmp_path):
    from app.config import settings

    monkeypatch.setattr(settings, "LESSON_ARTIFACT_ROOT", str(tmp_path / "lesson_artifacts"))
    pupil = create_test_pupil("No Document Transcript Student")
    lesson = create_test_lesson(pupil["id"])

    response = client.post(f"/api/lessons/{lesson['id']}/documents/generate", json={})

    assert response.status_code == 404
    assert response.json()["detail"] == "Completed lesson transcript not found"


def test_lesson_document_download_respects_teacher_scope(monkeypatch, tmp_path):
    from app.dependencies import get_current_teacher_id

    lesson, _ = create_transcribed_lesson(monkeypatch, tmp_path)
    documents = client.post(f"/api/lessons/{lesson['id']}/documents/generate", json={"allow_unreviewed": True}).json()

    app.dependency_overrides[get_current_teacher_id] = lambda: "other-teacher"
    try:
        response = client.get(documents[0]["download_url"])
        assert response.status_code == 404
        assert response.json()["detail"] == "Lesson not found"
    finally:
        app.dependency_overrides.pop(get_current_teacher_id, None)


def install_fake_job_service(monkeypatch, *, transcript_text: str = "Pipeline transcript", fail: bool = False):
    from app.routers import lessons as lessons_router
    from app.services.lesson_documents import LessonDocumentGenerationService
    from app.services.lesson_jobs import LessonProcessingJobService
    from app.services.transcription import FakeTranscriptionProvider, TranscriptionService

    service = LessonProcessingJobService(
        transcription_service=TranscriptionService(provider=FakeTranscriptionProvider(text=transcript_text, fail=fail)),
        document_service=LessonDocumentGenerationService(),
    )
    monkeypatch.setattr(lessons_router, "lesson_job_service", service)
    return service


def test_lesson_processing_job_can_be_created_queued_and_run_later(monkeypatch, tmp_path):
    import asyncio
    from app.config import settings
    from app.models import Lesson
    from app.schemas import LessonProcessingJobCreate
    from app.services.lesson_jobs import LessonProcessingJobService

    monkeypatch.setattr(settings, "LESSON_ARTIFACT_ROOT", str(tmp_path / "lesson_artifacts"))
    service = install_fake_job_service(monkeypatch, transcript_text="Deferred pipeline text")
    pupil = create_test_pupil("Deferred Job Student")
    lesson = create_test_lesson(pupil["id"], topic="Deferred topic")
    recording = upload_test_recording(lesson["id"], data=b"webm-data").json()

    db = SessionTesting()
    try:
        lesson_model = db.query(Lesson).filter(Lesson.id == lesson["id"]).one()
        job = service.create_job(
            db,
            lesson=lesson_model,
            request=LessonProcessingJobCreate(
                job_type="full_pipeline",
                recording_id=recording["id"],
                document_types=["check_list"],
            ),
        )
        assert job.status == "queued"
        assert job.stage == "queued"
        assert job.document_types == ["check_list"]

        runner = LessonProcessingJobService(
            transcription_service=service.transcription_service,
            document_service=service.document_service,
        )
        completed = asyncio.run(runner.run_existing_job(db, job_id=job.id))

        assert completed.status == "completed"
        assert completed.stage == "completed"
        assert completed.recording_id == recording["id"]
        assert completed.transcript_id
        assert len(completed.document_ids) == 1
    finally:
        db.close()


def test_lesson_processing_job_full_pipeline_and_polling(monkeypatch, tmp_path):
    from app.config import settings

    monkeypatch.setattr(settings, "LESSON_ARTIFACT_ROOT", str(tmp_path / "lesson_artifacts"))
    install_fake_job_service(monkeypatch, transcript_text="Pipeline x_1 & 50%")
    pupil = create_test_pupil("Job Student")
    lesson = create_test_lesson(pupil["id"], topic="Job & topic")
    recording = upload_test_recording(lesson["id"], data=b"webm-data").json()

    response = client.post(
        f"/api/lessons/{lesson['id']}/processing-jobs",
        json={"job_type": "full_pipeline", "recording_id": recording["id"]},
    )

    assert response.status_code == 202
    job = response.json()
    assert job["status"] == "completed"
    assert job["stage"] == "completed"
    assert job["recording_id"] == recording["id"]
    assert job["transcript_id"]
    assert len(job["document_ids"]) == 2
    assert job["attempts"] == 1

    poll_response = client.get(f"/api/lessons/{lesson['id']}/processing-jobs/{job['id']}")
    assert poll_response.status_code == 200
    assert poll_response.json()["id"] == job["id"]

    list_response = client.get(f"/api/lessons/{lesson['id']}/processing-jobs")
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == [job["id"]]

    documents_before = client.get(f"/api/lessons/{lesson['id']}/documents").json()
    second_response = client.post(f"/api/lessons/{lesson['id']}/processing-jobs", json={"job_type": "full_pipeline"})
    assert second_response.status_code == 202
    documents_after = client.get(f"/api/lessons/{lesson['id']}/documents").json()
    assert len(documents_before) == 2
    assert len(documents_after) == 2


def test_lesson_processing_job_records_failure(monkeypatch, tmp_path):
    from app.config import settings

    monkeypatch.setattr(settings, "LESSON_ARTIFACT_ROOT", str(tmp_path / "lesson_artifacts"))
    install_fake_job_service(monkeypatch, fail=True)
    pupil = create_test_pupil("Failed Job Student")
    lesson = create_test_lesson(pupil["id"])
    recording = upload_test_recording(lesson["id"], data=b"webm-data").json()

    response = client.post(
        f"/api/lessons/{lesson['id']}/processing-jobs",
        json={"job_type": "full_pipeline", "recording_id": recording["id"]},
    )

    assert response.status_code == 202
    job = response.json()
    assert job["status"] == "failed"
    assert job["stage"] == "failed"
    assert job["error_message"] == "Fake transcription provider failed"
    assert job["document_ids"] == []


def test_lesson_processing_job_respects_teacher_scope(monkeypatch, tmp_path):
    from app.config import settings
    from app.dependencies import get_current_teacher_id

    monkeypatch.setattr(settings, "LESSON_ARTIFACT_ROOT", str(tmp_path / "lesson_artifacts"))
    install_fake_job_service(monkeypatch)
    pupil = create_test_pupil("Scoped Job Student")
    lesson = create_test_lesson(pupil["id"])

    app.dependency_overrides[get_current_teacher_id] = lambda: "other-teacher"
    try:
        response = client.post(f"/api/lessons/{lesson['id']}/processing-jobs", json={"job_type": "full_pipeline"})
        assert response.status_code == 404
        assert response.json()["detail"] == "Lesson not found"
    finally:
        app.dependency_overrides.pop(get_current_teacher_id, None)


def test_create_file():
    project_response = client.post("/api/projects/", json={"name": "Test Project"})
    project_id = project_response.json()["id"]

    response = client.post(
        f"/api/files/project/{project_id}",
        json={"name": "test.tex", "content": r"\documentclass{article}\begin{document}Hello\end{document}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "test.tex"


def test_direct_file_access_respects_project_owner(monkeypatch):
    enable_trusted_proxy_auth(monkeypatch)
    owner_headers = {"X-Latexed-User": "teacher-a"}
    other_headers = {"X-Latexed-User": "teacher-b"}
    project_response = client.post("/api/projects/", json={"name": "Scoped File Project"}, headers=owner_headers)
    project_id = project_response.json()["id"]
    files_response = client.get(f"/api/files/project/{project_id}", headers=owner_headers)
    file_id = files_response.json()[0]["id"]

    assert client.get(f"/api/files/{file_id}", headers=owner_headers).status_code == 200
    assert client.get(f"/api/files/{file_id}", headers=other_headers).status_code == 404

    update_response = client.put(
        f"/api/files/{file_id}",
        json={"content": "Cross-user write must be denied"},
        headers=other_headers,
    )
    assert update_response.status_code == 404

    owner_file = client.get(f"/api/files/{file_id}", headers=owner_headers).json()
    assert owner_file["content"] != "Cross-user write must be denied"


def test_list_templates():
    response = client.get("/api/templates/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0


def test_create_file_rejects_unsafe_name():
    project_response = client.post("/api/projects/", json={"name": "Unsafe File Project"})
    project_id = project_response.json()["id"]

    response = client.post(
        f"/api/files/project/{project_id}",
        json={"name": "../secret.tex", "content": ""},
    )

    assert response.status_code == 400
    assert "Invalid LaTeX filename" in response.json()["detail"]


def test_file_service_keeps_single_main_file_invariant():
    project_response = client.post("/api/projects/", json={"name": "Main File Project"})
    project_id = project_response.json()["id"]

    response = client.post(
        f"/api/files/project/{project_id}",
        json={"name": "sections/lesson.tex", "content": "Lesson", "is_main": True},
    )

    assert response.status_code == 201
    files_response = client.get(f"/api/files/project/{project_id}")
    files = files_response.json()
    main_flags = {file["name"]: file["is_main"] for file in files}

    assert main_flags["sections/lesson.tex"] is True
    assert main_flags["main.tex"] is False


def test_latex_compiler_adds_russian_babel_environment_hint():
    from app.services.latex_compiler import LatexCompiler

    log_text = """
! Package babel Error: Unknown option 'russian'. Either you misspelled it
(babel)                or the language definition file russian.ldf was not found.
"""
    errors = LatexCompiler()._extract_errors(log_text)

    assert "Unknown option 'russian'" in errors
    assert "texlive-lang-cyrillic" in errors


def test_latex_compiler_adds_enumitem_list_true_source_hint():
    from app.services.latex_compiler import LatexCompiler

    log_text = """
! LaTeX Error: Unknown option `list=true' for package `enumitem'.
!  ==> Fatal error occurred, no output PDF file produced!
"""
    errors = LatexCompiler()._extract_errors(log_text)

    assert "Unknown option `list=true'" in errors
    assert "enumitem does not support package option list=true" in errors
    assert "\\usepackage{enumitem}" in errors


def test_latex_compiler_adds_microtype_font_expansion_hint():
    from app.services.latex_compiler import LatexCompiler

    log_text = """
! pdfTeX error (font expansion): auto expansion is only possible with scalable fonts.
!  ==> Fatal error occurred, no output PDF file produced!
"""
    errors = LatexCompiler()._extract_errors(log_text)

    assert "font expansion" in errors
    assert "\\usepackage[expansion=false]{microtype}" in errors


def test_latex_sanitizer_normalizes_known_package_options():
    from app.services.latex_sanitizer import sanitize_latex_source

    content = r"\usepackage[list=true,shortlabels]{enumitem}"

    assert sanitize_latex_source(content) == r"\usepackage[shortlabels]{enumitem}"
    assert sanitize_latex_source(r"\usepackage[list=true]{enumitem}") == r"\usepackage{enumitem}"
    assert sanitize_latex_source(r"\usepackage{microtype}") == r"\usepackage[expansion=false]{microtype}"
    assert sanitize_latex_source(r"\usepackage[protrusion=true,expansion=true]{microtype}") == (
        r"\usepackage[protrusion=true,expansion=false]{microtype}"
    )


def test_latex_sanitizer_normalizes_generated_body_artifacts():
    from app.services.latex_sanitizer import sanitize_generated_latex_body

    content = (
        "```latex\n"
        r"\documentclass{article}\usepackage{graphicx}\begin{document}"
        r"\begin{solution}x ≤ 2…\end{solution}"
        r"\begin{example}2 × 2 = 4\end{example}"
        r"\end{document}"
        "\n```"
    )

    sanitized = sanitize_generated_latex_body(content)

    assert r"\documentclass" not in sanitized
    assert r"\usepackage" not in sanitized
    assert r"\begin{document}" not in sanitized
    assert r"\begin{solution}" not in sanitized
    assert r"\textbf{Решение.}" in sanitized
    assert r"\begin{infoblock}{Пример}" in sanitized
    assert r"\le" in sanitized
    assert r"\times" in sanitized
    assert r"\ldots" in sanitized


def test_latex_sanitizer_simplifies_safe_mode_risky_fragments():
    from app.services.latex_sanitizer import sanitize_generated_latex_body_for_safe_mode

    content = (
        r"\section{Графики}"
        r"\begin{tikzpicture}\draw (0,0)--(1,1);\end{tikzpicture}"
        r"\includegraphics[width=5cm]{plot.png}"
        r"\input{extra.tex}"
    )

    sanitized = sanitize_generated_latex_body_for_safe_mode(content)

    assert r"\begin{tikzpicture}" not in sanitized
    assert r"\includegraphics" not in sanitized
    assert r"\input" not in sanitized
    assert r"\begin{infoblock}{Схема упрощена}" in sanitized
    assert r"\begin{infoblock}{Изображение пропущено}" in sanitized
    assert r"\begin{infoblock}{Вставка файла пропущена}" in sanitized


@pytest.mark.parametrize(
    ("fixture_name", "expect_valid", "expected_fragments", "unexpected_fragments", "expected_error"),
    [
        (
            "safe_special_chars.tex",
            True,
            [r"100\%", r"task\_1", r"\#3", r"$x_1 + y_2$"],
            ["100%", "task_1"],
            "",
        ),
        (
            "aliases_unicode.tex",
            True,
            [
                r"\begin{infoblock}{Определение}",
                r"\begin{infoblock}{Заметка}",
                r"$\le$",
                r"$\ne$",
                r"$\times$",
                r"$\to$",
                r"\ldots",
            ],
            ["≤", "≠", "×", "→", "…", r"\begin{definition}", r"\begin{note}"],
            "",
        ),
        (
            "risky_safe_fragments.tex",
            True,
            ["Схема упрощена", "Изображение пропущено"],
            [r"\begin{tikzpicture}", r"\includegraphics"],
            "",
        ),
        (
            "unbalanced_braces.tex",
            False,
            [],
            [],
            "Несбалансированные фигурные скобки",
        ),
        (
            "math_command_outside_math.tex",
            False,
            [],
            [],
            r"Математическая команда \frac найдена вне math mode",
        ),
    ],
)
def test_ai_output_failure_corpus_pipeline(fixture_name, expect_valid, expected_fragments, unexpected_fragments, expected_error):
    from app.services.latex_document_builder import build_latex_document
    from app.services.latex_sanitizer import sanitize_generated_latex_body, sanitize_generated_latex_body_for_safe_mode
    from app.services.latex_validator import validate_latex_document

    fixture_path = Path(__file__).parent / "fixtures" / "ai_outputs" / fixture_name
    raw_output = fixture_path.read_text(encoding="utf-8")

    body = sanitize_generated_latex_body(raw_output)
    body = sanitize_generated_latex_body_for_safe_mode(body)
    document = build_latex_document(body)
    validation = validate_latex_document(document, safe_mode=True)

    for fragment in expected_fragments:
        assert fragment in document
    for fragment in unexpected_fragments:
        assert fragment not in document
    assert validation["valid"] is expect_valid
    if expected_error:
        assert any(expected_error in error for error in validation["errors"])


def test_latex_validator_rejects_unbalanced_generated_environments_and_body_preamble():
    from app.services.latex_document_builder import build_latex_document
    from app.services.latex_validator import validate_latex_document

    document = build_latex_document(r"\usepackage{graphicx}\begin{infoblock}{Важно}Текст $x+1")
    validation = validate_latex_document(document)

    assert validation["valid"] is False
    assert any("Тело документа не должно содержать \\usepackage" in error for error in validation["errors"])
    assert any("Несбалансированное окружение infoblock" in error for error in validation["errors"])
    assert any("Несбалансированные inline math delimiters" in error for error in validation["errors"])


def test_latex_file_policy_rejects_path_traversal_and_unsupported_extensions():
    from app.services.latex_file_policy import LatexFilePolicyError, validate_latex_filename

    assert validate_latex_filename("sections/topic.tex") == "sections/topic.tex"

    for filename in ["../secret.tex", "/tmp/secret.tex", "bad\\name.tex", "image.png"]:
        try:
            validate_latex_filename(filename)
        except LatexFilePolicyError as exc:
            assert filename in str(exc)
        else:
            raise AssertionError(f"{filename} should be rejected")


def test_artifact_cleanup_removes_only_old_allowed_files(tmp_path):
    import os
    import time
    from app.services.artifact_cleanup import cleanup_old_files

    old_pdf = tmp_path / "old.pdf"
    new_pdf = tmp_path / "new.pdf"
    old_txt = tmp_path / "old.txt"
    nested_dir = tmp_path / "nested"
    nested_dir.mkdir()
    old_pdf.write_bytes(b"old")
    new_pdf.write_bytes(b"new")
    old_txt.write_text("old")

    old_time = time.time() - 3600
    os.utime(old_pdf, (old_time, old_time))
    os.utime(old_txt, (old_time, old_time))

    removed = cleanup_old_files(tmp_path, max_age_seconds=60, suffixes={".pdf"}, trusted_roots=(tmp_path,))

    assert removed == 1
    assert not old_pdf.exists()
    assert new_pdf.exists()
    assert old_txt.exists()
    assert nested_dir.exists()


def test_artifact_cleanup_rejects_untrusted_root(tmp_path):
    import pytest
    from app.services.artifact_cleanup import cleanup_old_files
    from app.services.artifact_paths import InvalidArtifactFilenameError

    trusted_root = tmp_path / "trusted"
    untrusted_root = tmp_path / "untrusted"
    trusted_root.mkdir()
    untrusted_root.mkdir()

    with pytest.raises(InvalidArtifactFilenameError):
        cleanup_old_files(untrusted_root, max_age_seconds=60, suffixes={".pdf"}, trusted_roots=(trusted_root,))


def test_artifact_cleanup_dry_run_reports_without_deleting(tmp_path):
    import os
    import time
    from app.services.artifact_cleanup import cleanup_old_files_report

    old_pdf = tmp_path / "old.pdf"
    old_pdf.write_bytes(b"old")
    old_time = time.time() - 3600
    os.utime(old_pdf, (old_time, old_time))

    report = cleanup_old_files_report(
        tmp_path,
        root_name="compile_pdf",
        max_age_seconds=60,
        suffixes={".pdf"},
        trusted_roots=(tmp_path,),
        dry_run=True,
    )

    assert report.dry_run is True
    assert report.would_delete_files == 1
    assert report.deleted_files == 0
    assert old_pdf.exists()


def test_artifact_cleanup_skips_symlink_escape(tmp_path):
    import os
    import time
    from app.services.artifact_cleanup import cleanup_old_files_report

    trusted_root = tmp_path / "trusted"
    outside = tmp_path / "outside"
    trusted_root.mkdir()
    outside.mkdir()
    outside_pdf = outside / "outside.pdf"
    outside_pdf.write_bytes(b"outside")
    symlink = trusted_root / "escape.pdf"
    symlink.symlink_to(outside_pdf)
    old_time = time.time() - 3600
    os.utime(symlink, (old_time, old_time), follow_symlinks=False)

    report = cleanup_old_files_report(
        trusted_root,
        max_age_seconds=60,
        suffixes={".pdf"},
        trusted_roots=(trusted_root,),
    )

    assert report.deleted_files == 0
    assert report.skipped_files == 1
    assert symlink.exists()
    assert outside_pdf.exists()


def test_configured_artifact_cleanup_includes_lesson_root_without_upload_wildcard(monkeypatch, tmp_path):
    from app.config import settings
    from app.services.artifact_paths import artifact_cleanup_policies, trusted_artifact_roots

    compile_root = tmp_path / "compiles"
    upload_root = tmp_path / "uploads"
    lesson_root = tmp_path / "custom_lessons"
    monkeypatch.setattr(settings, "COMPILE_WORK_DIR", str(compile_root))
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(upload_root))
    monkeypatch.setattr(settings, "LESSON_ARTIFACT_ROOT", str(lesson_root))

    policies = {policy.name: policy for policy in artifact_cleanup_policies()}

    assert set(policies) == {"compile_pdf", "export", "lesson"}
    assert policies["lesson"].root == lesson_root
    assert policies["lesson"].recursive is True
    assert upload_root not in trusted_artifact_roots()


def test_latex_compiler_truncates_compiler_output(monkeypatch, tmp_path):
    import subprocess
    from app.config import settings
    from app.services.latex_compiler import LatexCompiler

    compiler = LatexCompiler()
    monkeypatch.setattr(compiler, "work_dir", tmp_path)
    monkeypatch.setattr(settings, "MAX_COMPILER_OUTPUT_CHARS", 12)

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=args, returncode=1, stdout="0123456789abcdef", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = compiler.compile(r"\documentclass{article}\begin{document}Hi\end{document}")

    assert result.status == "error"
    assert result.output == "456789abcdef"


def test_latex_compiler_sanitizes_enumitem_list_true_before_pdflatex(monkeypatch, tmp_path):
    import subprocess
    from pathlib import Path
    from app.services.latex_compiler import LatexCompiler

    compiler = LatexCompiler()
    monkeypatch.setattr(compiler, "work_dir", tmp_path)

    def fake_run(*args, **kwargs):
        work_dir = Path(kwargs["cwd"])
        main_tex = (work_dir / "main.tex").read_text(encoding="utf-8")
        assert r"\usepackage[list=true]{enumitem}" not in main_tex
        assert r"\usepackage{enumitem}" in main_tex
        assert r"\usepackage{microtype}" not in main_tex
        assert r"\usepackage[expansion=false]{microtype}" in main_tex
        (work_dir / "main.pdf").write_bytes(b"%PDF-1.4 sanitized")
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = compiler.compile(
        r"\documentclass{article}\usepackage[list=true]{enumitem}\usepackage{microtype}\begin{document}Text\end{document}"
    )

    assert result.status == "success"


def test_latex_compiler_uses_selected_main_filename(monkeypatch, tmp_path):
    import subprocess
    from pathlib import Path
    from app.services.latex_compiler import LatexCompiler

    compiler = LatexCompiler()
    monkeypatch.setattr(compiler, "work_dir", tmp_path)

    def fake_run(args, **kwargs):
        work_dir = Path(kwargs["cwd"])
        assert args[-1] == "chapter.tex"
        assert (work_dir / "chapter.tex").read_text(encoding="utf-8") == "selected content"
        assert (work_dir / "main.tex").read_text(encoding="utf-8") == "old main"
        (work_dir / "chapter.pdf").write_bytes(b"%PDF-1.4 selected")
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = compiler.compile(
        "selected content",
        {"main.tex": "old main", "chapter.tex": "old chapter"},
        main_filename="chapter.tex",
    )

    assert result.status == "success"
    assert result.pdf_url


def test_latex_compiler_returns_typed_result_for_compiler_error(monkeypatch):
    from app.services.latex_compiler import LatexCompiler
    from app.schemas import LatexCompileResult

    compiler = LatexCompiler()
    monkeypatch.setattr(compiler, "compiler", "definitely-missing-pdflatex")

    result = compiler.compile(r"\documentclass{article}\begin{document}Hi\end{document}")

    assert isinstance(result, LatexCompileResult)
    assert result.status == "error"
    assert result.error


def test_pdf_generator_returns_typed_result_for_missing_pdf(monkeypatch, tmp_path):
    import subprocess
    from app.services.pdf_generator import PDFGenerator
    from app.schemas import PDFGenerationResult

    generator = PDFGenerator()
    monkeypatch.setattr(generator, "output_dir", tmp_path)

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = generator.generate_pdf(r"\documentclass{article}\begin{document}Hi\end{document}")

    assert isinstance(result, PDFGenerationResult)
    assert result.success is False
    assert result.error == "PDF was not generated"


def test_pdf_generator_sanitizes_enumitem_list_true_before_pdflatex(monkeypatch, tmp_path):
    import subprocess
    from pathlib import Path
    from app.services.pdf_generator import PDFGenerator

    generator = PDFGenerator()
    monkeypatch.setattr(generator, "output_dir", tmp_path)

    def fake_run(*args, **kwargs):
        work_dir = Path(kwargs["cwd"])
        main_tex = (work_dir / "main.tex").read_text(encoding="utf-8")
        assert r"\usepackage[list=true]{enumitem}" not in main_tex
        assert r"\usepackage{enumitem}" in main_tex
        assert r"\usepackage{microtype}" not in main_tex
        assert r"\usepackage[expansion=false]{microtype}" in main_tex
        (work_dir / "main.pdf").write_bytes(b"%PDF-1.4 sanitized")
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = generator.generate_pdf(
        r"\documentclass{article}\usepackage[list=true]{enumitem}\usepackage{microtype}\begin{document}Text\end{document}"
    )

    assert result.success is True
    assert result.filename


def test_compile_raw(monkeypatch):
    from app.routers import compile as compile_router

    content = r"""\documentclass{article}
\begin{document}
Hello World!
\end{document}"""

    def fake_compile(main_content, files):
        assert main_content == content
        assert files == {"chapter.tex": "Chapter text"}
        return {
            "status": "success",
            "output": "Compiled",
            "compile_time": "0.01s",
            "pdf_url": "/api/compile/download/test.pdf",
        }

    monkeypatch.setattr(compile_router.compiler, "compile", fake_compile)

    response = client.post(
        "/api/compile/raw",
        json={"content": content, "files": {"chapter.tex": "Chapter text"}},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["pdf_url"] == "/api/compile/download/test.pdf"


def test_compile_project_uses_requested_main_file_name(monkeypatch):
    from app.routers import compile as compile_router

    selected_content = r"\documentclass{article}\begin{document}Selected\end{document}"

    def fake_compile(main_content, files, main_filename="main.tex"):
        assert main_filename == "chapter.tex"
        assert main_content == selected_content
        assert files["main.tex"] != selected_content
        assert files["chapter.tex"] == selected_content
        return {
            "status": "success",
            "output": "Compiled selected",
            "compile_time": "0.01s",
            "pdf_url": "/api/compile/download/selected.pdf",
        }

    monkeypatch.setattr(compile_router.compiler, "compile", fake_compile)

    project_response = client.post(
        "/api/projects/",
        json={"name": "Selected Compile Project", "template": "article"},
    )
    project_id = project_response.json()["id"]

    response = client.post(
        "/api/compile/",
        json={
            "project_id": project_id,
            "main_file_name": "chapter.tex",
            "main_file_content": selected_content,
            "all_files": {
                "main.tex": r"\documentclass{article}\begin{document}Main\end{document}",
                "chapter.tex": selected_content,
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["pdf_url"] == "/api/compile/download/selected.pdf"


def test_compile_project_respects_project_owner(monkeypatch):
    enable_trusted_proxy_auth(monkeypatch)
    from app.routers import compile as compile_router

    called = False

    def fake_compile(main_content, files, main_filename="main.tex"):
        nonlocal called
        called = True
        return {"status": "success", "output": "Compiled", "compile_time": "0.01s"}

    monkeypatch.setattr(compile_router.compiler, "compile", fake_compile)
    owner_headers = {"X-Latexed-User": "teacher-a"}
    other_headers = {"X-Latexed-User": "teacher-b"}
    project_response = client.post(
        "/api/projects/",
        json={"name": "Scoped Compile Project", "template": "article"},
        headers=owner_headers,
    )
    project_id = project_response.json()["id"]

    response = client.post("/api/compile/", json={"project_id": project_id}, headers=other_headers)

    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found"
    assert called is False


def test_compile_raw_rejects_too_many_files(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "MAX_LATEX_FILES", 1)

    response = client.post(
        "/api/compile/raw",
        json={
            "content": r"\documentclass{article}\begin{document}Main\end{document}",
            "files": {"notes.tex": "Notes"},
        },
    )

    assert response.status_code == 413
    assert "Too many LaTeX files" in response.json()["detail"]


def test_compile_raw_rejects_oversized_entrypoint(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "MAX_LATEX_FILE_CHARS", 10)

    response = client.post(
        "/api/compile/raw",
        json={
            "content": r"\documentclass{article}\begin{document}Too large\end{document}",
            "files": {},
        },
    )

    assert response.status_code == 413
    assert "__entrypoint__.tex" in response.json()["detail"]
    assert "too large" in response.json()["detail"]


def test_compile_raw_rejects_unsupported_payload_extension():
    response = client.post(
        "/api/compile/raw",
        json={
            "content": r"\documentclass{article}\begin{document}Main\end{document}",
            "files": {"image.png": "not binary"},
        },
    )

    assert response.status_code == 400
    assert "Unsupported LaTeX file extension" in response.json()["detail"]


def test_compile_project_rejects_traversal_main_filename():
    project_response = client.post(
        "/api/projects/",
        json={"name": "Traversal Compile Project", "template": "article"},
    )
    project_id = project_response.json()["id"]

    response = client.post(
        "/api/compile/",
        json={
            "project_id": project_id,
            "main_file_name": "../main.tex",
            "main_file_content": r"\documentclass{article}\begin{document}Main\end{document}",
        },
    )

    assert response.status_code == 400
    assert "Invalid LaTeX filename" in response.json()["detail"]


def test_export_tex_rejects_unsupported_filename_extension():
    project_response = client.post(
        "/api/projects/",
        json={"name": "Unsupported Export Project", "template": "article"},
    )
    project_id = project_response.json()["id"]

    response = client.post(
        "/api/export/tex",
        json={"project_id": project_id, "format": "tex", "content": {"notes.exe": "bad"}},
    )

    assert response.status_code == 400
    assert "Unsupported LaTeX file extension" in response.json()["detail"]


def test_export_tex_rejects_payload_over_total_limit(monkeypatch):
    from app.config import settings

    project_response = client.post(
        "/api/projects/",
        json={"name": "Oversized Export Project", "template": "article"},
    )
    project_id = project_response.json()["id"]
    monkeypatch.setattr(settings, "MAX_LATEX_TOTAL_CHARS", 10)

    response = client.post(
        "/api/export/tex",
        json={"project_id": project_id, "format": "tex", "content": {"main.tex": "x" * 20}},
    )

    assert response.status_code == 413
    assert "LaTeX payload is too large" in response.json()["detail"]


def test_compile_history_project_and_item_routes(monkeypatch):
    from app.routers import compile as compile_router

    def fake_compile(main_content, files, main_filename="main.tex"):
        assert main_filename == "main.tex"
        return {
            "status": "success",
            "output": "Compiled",
            "compile_time": "0.01s",
            "pdf_url": "/api/compile/download/test.pdf",
        }

    monkeypatch.setattr(compile_router.compiler, "compile", fake_compile)

    project_response = client.post(
        "/api/projects/",
        json={"name": "Compile History Project", "template": "article"},
    )
    project_id = project_response.json()["id"]

    compile_response = client.post(
        "/api/compile/",
        json={"project_id": project_id},
    )
    assert compile_response.status_code == 200
    history_id = compile_response.json()["history_id"]

    project_history_response = client.get(f"/api/compile/history/project/{project_id}")
    assert project_history_response.status_code == 200
    project_history = project_history_response.json()
    assert len(project_history) == 1
    assert project_history[0]["id"] == history_id

    history_item_response = client.get(f"/api/compile/history/item/{history_id}")
    assert history_item_response.status_code == 200
    assert history_item_response.json()["project_id"] == project_id


def test_compile_pdf_download_serves_existing_pdf(tmp_path, monkeypatch):
    from app.routers import compile as compile_router

    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()
    pdf_file = pdf_dir / "compiled.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 test pdf")
    monkeypatch.setattr(compile_router.settings, "COMPILE_WORK_DIR", str(tmp_path))

    response = client.get("/api/compile/download/compiled.pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"].startswith('inline; filename="compiled.pdf"')
    assert response.content == b"%PDF-1.4 test pdf"


def test_compile_pdf_download_rejects_invalid_filename():
    response = client.get("/api/compile/download/not-a-pdf.txt")
    assert response.status_code == 400


def test_artifact_download_resolver_rejects_traversal_and_unsupported_types(tmp_path, monkeypatch):
    import pytest
    from app.config import settings
    from app.services.artifact_paths import (
        InvalidArtifactFilenameError,
        UnsupportedArtifactTypeError,
        resolve_artifact_download,
    )

    monkeypatch.setattr(settings, "COMPILE_WORK_DIR", str(tmp_path / "compile"))
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path / "uploads"))

    compile_target = resolve_artifact_download("compile_pdf", "compiled.pdf")
    assert compile_target.path == (tmp_path / "compile" / "pdfs" / "compiled.pdf").resolve()
    assert compile_target.media_type == "application/pdf"
    assert compile_target.content_disposition_type == "inline"

    export_target = resolve_artifact_download("export", "document.html")
    assert export_target.path == (tmp_path / "uploads" / "exports" / "document.html").resolve()
    assert export_target.media_type == "text/html"

    for unsafe_name in ["../evil.pdf", "nested/evil.pdf", r"nested\evil.pdf", " evil.pdf", "evil.pdf\n"]:
        with pytest.raises(InvalidArtifactFilenameError):
            resolve_artifact_download("compile_pdf", unsafe_name)

    with pytest.raises(UnsupportedArtifactTypeError):
        resolve_artifact_download("compile_pdf", "compiled.html")
    with pytest.raises(UnsupportedArtifactTypeError):
        resolve_artifact_download("export", "payload.txt")
    with pytest.raises(UnsupportedArtifactTypeError):
        resolve_artifact_download("export", "source.tex")


def test_frontend_bootstrap_contract_creates_template_project_and_updates_main_file():
    project_response = client.post(
        "/api/projects/",
        json={"name": "Frontend Runtime Project", "template": "article"},
    )
    assert project_response.status_code == 201
    project_id = project_response.json()["id"]

    files_response = client.get(f"/api/files/project/{project_id}")
    assert files_response.status_code == 200
    files = files_response.json()
    assert len(files) == 1
    main_file = files[0]
    assert main_file["name"] == "main.tex"
    assert main_file["is_main"] is True
    assert "\\documentclass" in main_file["content"]

    updated_content = r"\documentclass{article}\begin{document}Updated\end{document}"
    update_response = client.put(
        f"/api/files/{main_file['id']}",
        json={"content": updated_content},
    )
    assert update_response.status_code == 200
    assert update_response.json()["content"] == updated_content


def test_frontend_generation_ui_contract():
    frontend_dir = Path(__file__).resolve().parents[2] / "frontend"
    frontend_html = frontend_dir / "main.html"
    frontend_js_files = sorted((frontend_dir / "js").glob("*.js"))
    content = "\n".join(
        [
            frontend_html.read_text(encoding="utf-8"),
            (frontend_dir / "css/app.css").read_text(encoding="utf-8"),
            *(path.read_text(encoding="utf-8") for path in frontend_js_files),
        ]
    )

    assert 'href="css/app.css"' in content
    assert 'src="js/01-state.js?v=' in content
    assert 'src="js/09-ui-settings.js?v=' in content
    assert 'id="generationModal"' in content
    assert 'id="generationTopic"' in content
    assert 'id="generationMaterials"' in content
    assert 'id="generationMaterialsHint"' in content
    assert 'oninput="updateGenerationMaterialsDiagnostics()"' in content
    assert 'id="generationLanguage"' in content
    assert 'id="generationContentSourceMode"' in content
    assert 'id="generationLatexMode"' in content
    assert 'value="safe" selected' in content
    assert 'value="rich"' in content
    assert 'value="qwen2.5:3b"' in content
    assert "collectGenerationRequest" in content
    assert "generateLatexFromAi" in content
    assert "main_file_name" in content
    assert "validateCurrentLatex" in content
    assert "checkGenerationProvider" in content
    assert 'id="generationInsertMode"' in content
    assert "language: getGenerationFieldValue('generationLanguage')" in content
    assert "content_source_mode: getGenerationFieldValue('generationContentSourceMode')" in content
    assert "latex_mode: getGenerationFieldValue('generationLatexMode')" in content
    assert 'id="generationFilename"' in content
    assert "copyGenerationPrompt" in content
    assert "copyGenerationRawOutput" in content
    assert 'id="retryGenerationBtn"' in content
    assert 'id="regenerateSafeBtn"' in content
    assert 'id="regenerateRichBtn"' in content
    assert 'id="insertLastGeneratedBtn"' in content
    assert "retryLastGeneration" in content
    assert "regenerateWithLatexMode" in content
    assert "insertLastGeneratedLatex" in content
    assert "setGenerationRetryActionsVisible" in content
    assert "generationNeedsUserDecision" in content
    assert "compile_check" in content
    assert "token_usage" in content
    assert "describeTokenUsage" in content
    assert "Токены за генерацию" in content
    assert "startGenerationFunWait" in content
    assert "TeX-единорога" in content
    assert "Разогреваю LaTeX-котёл" in content
    assert "applyGeneratedLatex" in content
    assert "createFileWithContent" in content
    assert 'id="documentInsightModal"' in content
    assert 'id="documentInsightPrompt"' in content
    assert "event.stopPropagation(); contextAction('inspect')" in content
    assert "inspectContextDocument" in content
    assert "openDocumentInsightModal" in content
    assert "await inspectContextDocument(contextMenuFileId)" in content
    assert "documentInsightModal {" in content
    assert "z-index: 1003" in content
    assert "loadLatestGenerationInsight" in content
    assert "AI-прогоны" in content
    assert "Токены всего" in content
    assert "generationMeta" in content
    assert "'/generation/validate'" in content
    assert "generation/providers/status" in content
    assert "'/generation/jobs'" in content
    assert "`/generation/jobs/${encodeURIComponent(currentJob.id)}`" in content
    assert "await compileLatex();" not in content
    assert "Соединение с backend установлено. Нажмите «Компиляция»" in content
    assert "Документ открыт без автокомпиляции" in content
    assert "ensureAdjacentPreviewVisible" in content
    assert "pdf.min.js" in content
    assert "pdf.worker.min.js" in content
    assert "pdfPreviewDocument" in content
    assert "window.pdfPreviewRenderTask" in content
    assert "loadPdfPreview" in content
    assert "pdfjsLib.getDocument" in content
    assert "pdf-preview-frame" in content
    assert "pdf-preview-container" in content
    assert "pdf-preview-shell" in content
    assert "pdf-preview-toolbar" in content
    assert "pdf-preview-canvas" in content
    assert "changePdfPreviewZoom" in content
    assert "setPdfPreviewFit('width')" in content
    assert "overflow: hidden" in content
    preview_content = "\n".join(
        (frontend_dir / path).read_text(encoding="utf-8")
        for path in ["js/02-api.js", "js/05-compile-preview.js", "js/06-toolbar-view.js"]
    )
    assert "window.open" not in preview_content


def _generation_job_payload(project_id: str, *, materials: str = "Материалы для генерации") -> dict:
    return {
        "project_id": project_id,
        "provider": "ollama",
        "materials": materials,
        "fields": {
            "level": "ЕГЭ",
            "language": "русский",
            "content_source_mode": "materials_only",
            "latex_mode": "safe",
            "alpha_code": 1,
            "beta_code": 1,
            "gamma_code": 4,
            "grade": "11 класс",
            "subject": "математика",
            "topic": "Квадратные уравнения",
            "priority_method": "нейросеть выбирает самостоятельно по отношению к уровню и классу",
            "graph_analytic": "по ситуации",
        },
    }


def test_create_generation_job_queues_without_running_provider(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "AI_GENERATION_JOB_EXECUTION_MODE", "external")

    project_response = client.post("/api/projects/", json={"name": "Generation Job Project"})
    assert project_response.status_code == 201
    project_id = project_response.json()["id"]

    response = client.post(
        "/api/generation/jobs",
        json=_generation_job_payload(project_id, materials="Уникальные материалы для queued job"),
    )

    assert response.status_code == 202
    data = response.json()
    assert data["id"]
    assert data["project_id"] == project_id
    assert data["status"] == "queued"
    assert data["stage"] == "queued"
    assert data["request_hash"]
    assert data["prompt_hash"]
    assert data["attempts"] == 0


def test_create_generation_job_replays_existing_idempotency_key(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "AI_GENERATION_JOB_EXECUTION_MODE", "external")

    project_response = client.post("/api/projects/", json={"name": "Idempotent Generation Job Project"})
    assert project_response.status_code == 201
    project_id = project_response.json()["id"]

    payload = _generation_job_payload(project_id, materials="Материалы для idempotency replay")
    headers = {"Idempotency-Key": "generation-job-replay-1"}

    first_response = client.post("/api/generation/jobs", json=payload, headers=headers)
    second_response = client.post("/api/generation/jobs", json=payload, headers=headers)

    assert first_response.status_code == 202
    assert second_response.status_code == 202
    first = first_response.json()
    second = second_response.json()
    assert second["id"] == first["id"]
    assert second["request_hash"] == first["request_hash"]
    assert second["idempotency_key"] == "generation-job-replay-1"


def test_generation_jobs_operator_status_returns_summary(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "AI_GENERATION_JOB_EXECUTION_MODE", "external")
    monkeypatch.setattr(settings, "AI_GENERATION_JOB_STALE_AFTER_SECONDS", 60)

    response = client.get("/api/generation/jobs/operator/status")

    assert response.status_code == 200
    data = response.json()
    assert data["execution_mode"] == "external"
    assert data["stale_after_seconds"] == 60
    assert data["counts"] == {
        "queued": 0,
        "running": 0,
        "completed": 0,
        "failed": 0,
        "canceled": 0,
    }
    assert data["backlog"] == 0
    assert data["stale_running"] == 0
    assert data["stale_samples"] == []


def test_generation_router_hotfix_artifacts_are_not_present():
    source = (Path(__file__).resolve().parents[2] / "backend" / "app" / "routers" / "generation.py").read_text(
        encoding="utf-8"
    )
    operator_status_source = source.split("@router.get(\"/jobs/operator/status\"", 1)[1].split(
        "@router.post(\"/jobs/operator/recover-stale\"",
        1,
    )[0]

    assert "create_job(\n            db,\n            job=job" not in source
    assert "return [generation_job_service.to_response(job) for job in jobs]" not in operator_status_source


def test_export_pdf_receives_frontend_content_payload(monkeypatch):
    from app.routers import export as export_router

    project_response = client.post(
        "/api/projects/",
        json={"name": "PDF Export Project", "template": "article"},
    )
    project_id = project_response.json()["id"]
    frontend_content = r"\documentclass{article}\begin{document}Fresh PDF\end{document}"

    def fake_generate_pdf(main_content, files):
        assert main_content == frontend_content
        assert files["main.tex"] == frontend_content
        assert files["notes.tex"] == "Notes"
        return {"success": True, "filename": "compiled.pdf", "size": 123}

    monkeypatch.setattr(export_router.pdf_generator, "generate_pdf", fake_generate_pdf)

    response = client.post(
        "/api/export/pdf",
        json={
            "project_id": project_id,
            "format": "pdf",
            "content": {"main.tex": frontend_content, "notes.tex": "Notes"},
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["url"] == "/api/export/download/compiled.pdf"
    assert data["format"] == "pdf"


def test_export_html_uses_frontend_content_payload(tmp_path, monkeypatch):
    from app.config import settings
    from app.routers import export as export_router

    project_response = client.post(
        "/api/projects/",
        json={"name": "HTML Export Project", "template": "article"},
    )
    project_id = project_response.json()["id"]
    frontend_content = r"\documentclass{article}\begin{document}Fresh HTML\end{document}"

    def fake_generate_html(main_content):
        assert main_content == frontend_content
        return "<html>Fresh HTML</html>"

    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(export_router.pdf_generator, "generate_html", fake_generate_html)

    response = client.post(
        "/api/export/html",
        json={
            "project_id": project_id,
            "format": "html",
            "content": {"main.tex": frontend_content},
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["format"] == "html"
    exported = tmp_path / "exports" / data["filename"]
    assert exported.read_text(encoding="utf-8") == "<html>Fresh HTML</html>"


def test_export_tex_uses_frontend_content_payload(tmp_path, monkeypatch):
    from app.config import settings
    from zipfile import ZipFile

    project_response = client.post(
        "/api/projects/",
        json={"name": "TEX Export Project", "template": "article"},
    )
    project_id = project_response.json()["id"]
    frontend_content = r"\documentclass{article}\begin{document}Fresh TEX\end{document}"

    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))

    response = client.post(
        "/api/export/tex",
        json={
            "project_id": project_id,
            "format": "tex",
            "content": {"main.tex": frontend_content, "notes.tex": "Notes"},
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["format"] == "tex"

    exported = tmp_path / "exports" / data["filename"]
    with ZipFile(exported) as archive:
        assert archive.read("main.tex").decode("utf-8") == frontend_content
        assert archive.read("notes.tex").decode("utf-8") == "Notes"


def test_export_html_respects_project_owner(monkeypatch):
    enable_trusted_proxy_auth(monkeypatch)
    from app.routers import export as export_router

    called = False

    def fake_generate_html(main_content):
        nonlocal called
        called = True
        return "<html>denied</html>"

    monkeypatch.setattr(export_router.pdf_generator, "generate_html", fake_generate_html)
    owner_headers = {"X-Latexed-User": "teacher-a"}
    other_headers = {"X-Latexed-User": "teacher-b"}
    project_response = client.post(
        "/api/projects/",
        json={"name": "Scoped Export Project", "template": "article"},
        headers=owner_headers,
    )
    project_id = project_response.json()["id"]

    response = client.post(
        "/api/export/html",
        json={"project_id": project_id, "format": "html"},
        headers=other_headers,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found"
    assert called is False


def test_export_tex_rejects_path_traversal_filename(tmp_path, monkeypatch):
    from app.config import settings

    project_response = client.post(
        "/api/projects/",
        json={"name": "Unsafe TEX Export Project", "template": "article"},
    )
    project_id = project_response.json()["id"]

    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))

    response = client.post(
        "/api/export/tex",
        json={
            "project_id": project_id,
            "format": "tex",
            "content": {"../evil.tex": "Bad"},
        },
    )

    assert response.status_code == 400
    assert "Invalid export filename" in response.json()["detail"]


def test_export_download_serves_existing_export_file(tmp_path, monkeypatch):
    from app.config import settings

    export_dir = tmp_path / "exports"
    export_dir.mkdir()
    export_file = export_dir / "document.html"
    export_file.write_text("<html>ok</html>", encoding="utf-8")
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))

    response = client.get("/api/export/download/document.html")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.text == "<html>ok</html>"


def test_export_download_rejects_unsupported_file_type(tmp_path, monkeypatch):
    from app.config import settings

    export_dir = tmp_path / "exports"
    export_dir.mkdir()
    (export_dir / "payload.txt").write_text("not an export", encoding="utf-8")
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))

    response = client.get("/api/export/download/payload.txt")

    assert response.status_code == 400
    assert response.json()["detail"] == "Unsupported export file type"


def test_export_download_rejects_path_traversal_filename():
    response = client.get(r"/api/export/download/nested\evil.zip")

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid export filename"


def test_snapshot_endpoints_use_typed_contracts():
    project_response = client.post(
        "/api/projects/",
        json={"name": "Snapshot Project", "template": "article"},
    )
    project_id = project_response.json()["id"]

    create_response = client.post(
        f"/api/projects/{project_id}/snapshot",
        json={"name": "Manual snapshot", "data": {"files": []}},
    )

    assert create_response.status_code == 201
    snapshot = create_response.json()
    assert snapshot["project_id"] == project_id
    assert snapshot["name"] == "Manual snapshot"
    assert "id" in snapshot
    assert "created_at" in snapshot

    list_response = client.get(f"/api/projects/{project_id}/snapshots")
    assert list_response.status_code == 200
    snapshots = list_response.json()
    assert len(snapshots) == 1
    assert snapshots[0]["id"] == snapshot["id"]
    assert snapshots[0]["project_id"] == project_id


def test_snapshot_rejects_mismatched_body_project_id():
    project_response = client.post(
        "/api/projects/",
        json={"name": "Snapshot Project", "template": "article"},
    )
    project_id = project_response.json()["id"]

    response = client.post(
        f"/api/projects/{project_id}/snapshot",
        json={"project_id": "00000000-0000-0000-0000-000000000000", "data": {}},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Snapshot project_id does not match path project_id"


def test_generation_presets():
    response = client.get("/api/generation/presets")
    assert response.status_code == 200
    presets = response.json()
    assert len(presets) >= 1
    assert presets[0]["id"] == "ege_math_11_hard"
    assert presets[0]["defaults"]["gamma_code"] == 4
    assert presets[0]["defaults"]["language"] == "русский"
    assert presets[0]["defaults"]["content_source_mode"] == "materials_only"
    assert presets[0]["defaults"]["latex_mode"] == "safe"


def test_generation_prompt_logs_safe_summary(caplog, monkeypatch):
    from app.routers import generation as generation_router

    monkeypatch.setattr(generation_router.settings, "AI_LOG_PROMPT_PREVIEW_CHARS", 0)
    caplog.set_level("INFO", logger="app.routers.generation")

    response = client.post(
        "/api/generation/prompt",
        json={
            "fields": {"topic": "Логарифмы"},
            "materials": "Решить log_2(x)=3.",
        },
    )
    assert response.status_code == 200

    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "ai prompt preview requested" in messages
    assert "ai prompt built" in messages
    assert "topic=Логарифмы" in messages
    assert "prompt_sha=" in messages


def test_generation_prompt_warns_against_invalid_enumitem_list_true_option():
    response = client.post(
        "/api/generation/prompt",
        json={"fields": {"topic": "Списки"}, "materials": "Сделать памятку."},
    )

    assert response.status_code == 200
    prompt = response.json()["prompt"]
    assert r"\usepackage[list=true]{enumitem}" not in prompt
    assert r"\usepackage[expansion=false]{microtype}" in prompt
    assert "невалидная опция enumitem" in prompt


def test_generation_prompt_includes_style_reference_latex():
    response = client.post(
        "/api/generation/prompt",
        json={"fields": {"topic": "Квадратные уравнения"}, "materials": "Сделать пособие."},
    )

    assert response.status_code == 200
    prompt = response.json()["prompt"]
    assert "РЕФЕРЕНС СТИЛЯ И ОФОРМЛЕНИЯ" in prompt
    assert "<STYLE_REFERENCE_LATEX>" in prompt
    assert r"\documentclass[a4paper,11pt]{article}" in prompt
    assert r"\usepackage{helvet}" in prompt
    assert r"\geometry{" in prompt
    assert "margin=2.3cm" in prompt
    assert r"\onehalfspacing" in prompt
    assert r"\newenvironment{infoblock}" in prompt
    assert r"\newenvironment{taskblock}" in prompt
    assert r"\newcommand{\answer}" in prompt
    assert "Обучающее пособие для углублённого изучения" in prompt
    assert "Не выводите преамбулу из референса" in prompt
    assert "backend добавит фиксированный технический минимум" in prompt


def test_generation_prompt_preview_includes_fields_and_materials():
    response = client.post(
        "/api/generation/prompt",
        json={
            "provider": "ollama",
            "model": "qwen2.5:14b",
            "fields": {
                "topic": "Показательные неравенства",
                "student_name": "Михаил Романов",
                "subject": "математика",
                "alpha_code": 1,
                "beta_code": 1,
                "gamma_code": 4,
            },
            "materials": "Решить неравенство 2^x > 8.",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["provider"] == "ollama"
    assert data["model"] == "qwen2.5:14b"
    assert data["warnings"] == []
    assert "Показательные неравенства" in data["prompt"]
    assert "Михаил Романов" in data["prompt"]
    assert "Язык пособия: русский" in data["prompt"]
    assert "Режим LaTeX-компилируемости: safe" in data["prompt"]
    assert "ЯЗЫК ДОКУМЕНТА" in data["prompt"]
    assert "РЕЖИМ LATEX: safe" in data["prompt"]
    assert "Режим источника содержания: materials_only" in data["prompt"]
    assert "строго только по материалам пользователя" in data["prompt"]
    assert "Решить неравенство 2^x > 8." in data["prompt"]
    assert "```latex```" in data["prompt"]
    assert "верните только тело LaTeX-документа" in data["prompt"]
    assert "Строго НЕ пишите преамбулу" in data["prompt"]


def test_generation_prompt_allows_ai_creative_source_mode_without_materials_warning():
    response = client.post(
        "/api/generation/prompt",
        json={
            "fields": {
                "topic": "Квадратные уравнения",
                "language": "английский",
                "content_source_mode": "ai_creative",
            },
            "materials": "",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["warnings"] == []
    assert "Язык пособия: английский" in data["prompt"]
    assert "Режим источника содержания: ai_creative" in data["prompt"]
    assert "Режим LaTeX-компилируемости: safe" in data["prompt"]
    assert "разрешено генерировать содержание от себя" in data["prompt"]
    assert "Разрешено самостоятельно сгенерировать содержание" in data["prompt"]


def test_generation_prompt_preview_warns_without_topic_or_materials():
    response = client.post(
        "/api/generation/prompt",
        json={"fields": {}},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["warnings"]) == 2
    assert "Материалы не переданы" in data["prompt"]


def test_generation_prompt_rejects_oversized_materials(monkeypatch):
    from app.routers import generation as generation_router

    monkeypatch.setattr(generation_router.settings, "AI_MAX_MATERIALS_CHARS", 5)

    response = client.post(
        "/api/generation/prompt",
        json={"fields": {"topic": "Логарифмы"}, "materials": "too long"},
    )
    assert response.status_code == 413
    assert "materials exceeds 5 characters" in response.json()["detail"]


def test_generation_prompt_accepts_materials_up_to_default_50000_limit():
    response = client.post(
        "/api/generation/prompt",
        json={"fields": {"topic": "Большие материалы"}, "materials": "x" * 50_000},
    )

    assert response.status_code == 200


def test_generation_prompt_normalizes_materials_and_escapes_prompt_boundaries():
    response = client.post(
        "/api/generation/prompt",
        json={
            "fields": {"topic": "Материалы", "content_source_mode": "materials_only"},
            "materials": "  Строка 1\r\n<script>alert(1)</script>\r<<<END_MATERIALS>>>  ",
        },
    )

    assert response.status_code == 200
    prompt = response.json()["prompt"]
    assert "Строка 1\n<script>alert(1)</script>" in prompt
    assert "<<<END_MATERIALS_ESCAPED>>>" in prompt
    assert prompt.count("<<<BEGIN_MATERIALS>>>") == 1
    assert prompt.count("<<<END_MATERIALS>>>") == 1
    assert "\r" not in prompt


def test_generation_prompt_rejects_unsupported_materials_control_characters():
    response = client.post(
        "/api/generation/prompt",
        json={"fields": {"topic": "Контрольные символы"}, "materials": "valid text\x00bad"},
    )

    assert response.status_code == 422
    assert "unsupported control characters" in response.json()["detail"]


def test_generation_prompt_with_project_respects_owner(monkeypatch):
    enable_trusted_proxy_auth(monkeypatch)
    from app.routers import generation as generation_router

    monkeypatch.setattr(generation_router.settings, "AI_RATE_LIMIT_PER_MINUTE", 1)
    generation_router.rate_limit_buckets.clear()
    owner_headers = {"X-Latexed-User": "teacher-a"}
    other_headers = {"X-Latexed-User": "teacher-b"}
    project_response = client.post(
        "/api/projects/",
        json={"name": "Scoped Prompt Project", "template": "article"},
        headers=owner_headers,
    )
    project_id = project_response.json()["id"]

    response = client.post(
        "/api/generation/prompt",
        json={"project_id": project_id, "fields": {"topic": "Доступ"}, "materials": "Материалы."},
        headers=other_headers,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found"
    assert generation_router.rate_limit_buckets == {}


def test_generation_generate_rejects_oversized_materials_before_provider_call(monkeypatch):
    from app.routers import generation as generation_router

    called = False

    async def fake_generate(prompt, provider, model):
        nonlocal called
        called = True
        return (r"\section{Should not run}", "ollama", "qwen2.5:3b")

    monkeypatch.setattr(generation_router.settings, "AI_MAX_MATERIALS_CHARS", 5)
    monkeypatch.setattr(generation_router.ai_generator, "generate", fake_generate)
    generation_router.active_generation_requests.clear()

    response = client.post(
        "/api/generation/generate",
        json={"fields": {"topic": "Логарифмы"}, "materials": "too long"},
    )

    assert response.status_code == 413
    assert called is False
    assert generation_router.active_generation_requests == {}


def test_generation_rate_limit_rejects_excess_requests(monkeypatch):
    from app.routers import generation as generation_router

    monkeypatch.setattr(generation_router.settings, "AI_RATE_LIMIT_PER_MINUTE", 1)
    generation_router.rate_limit_buckets.clear()

    first_response = client.post(
        "/api/generation/prompt",
        json={"fields": {"topic": "Логарифмы"}},
    )
    second_response = client.post(
        "/api/generation/prompt",
        json={"fields": {"topic": "Большие материалы"}, "materials": "x" * 50_000},
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 429
    assert second_response.headers["Retry-After"].isdigit()
    assert second_response.json()["detail"].startswith("AI rate limit exceeded. Try again in ")
    generation_router.rate_limit_buckets.clear()


def test_generation_generate_rejects_duplicate_in_flight_without_rate_limit_increment(monkeypatch):
    from app.config import settings
    from app.routers import generation as generation_router

    started = threading.Event()
    release = threading.Event()
    calls = 0

    async def fake_generate(prompt, provider, model):
        nonlocal calls
        calls += 1
        started.set()
        assert release.wait(timeout=5), "timed out waiting to release first generation request"
        return (
            "```latex\n"
            r"\section{Duplicate guard}Only one provider call"
            "\n```",
            "ollama",
            "qwen2.5:3b",
        )

    monkeypatch.setattr(settings, "AI_COMPILE_CHECK_ENABLED", False)
    monkeypatch.setattr(generation_router.ai_generator, "generate", fake_generate)
    generation_router.rate_limit_buckets.clear()
    generation_router.active_generation_requests.clear()

    payload = {
        "fields": {"topic": "Дубликаты", "content_source_mode": "materials_only"},
        "materials": "Пользовательские материалы должны отправляться только один раз.",
    }
    first_result = {}

    def send_first_request():
        first_result["response"] = client.post("/api/generation/generate", json=payload)

    thread = threading.Thread(target=send_first_request)
    thread.start()
    try:
        assert started.wait(timeout=5), "first generation request did not reach provider"

        duplicate_response = client.post("/api/generation/generate", json=payload)

        assert duplicate_response.status_code == 409
        assert duplicate_response.headers["Retry-After"] == str(
            generation_router.GENERATION_DUPLICATE_RETRY_AFTER_SECONDS
        )
        assert duplicate_response.json()["detail"] == (
            "AI generation is already running for the same input. Wait for the current request to finish."
        )
        assert calls == 1
        assert sum(len(bucket) for bucket in generation_router.rate_limit_buckets.values()) == 1
    finally:
        release.set()
        thread.join(timeout=5)
        generation_router.rate_limit_buckets.clear()
        generation_router.active_generation_requests.clear()

    assert not thread.is_alive()
    assert first_result["response"].status_code == 200
    assert calls == 1


def test_generation_prompt_normalizes_materials_and_escapes_prompt_boundaries():
    response = client.post(
        "/api/generation/prompt",
        json={
            "fields": {"topic": "Материалы", "content_source_mode": "materials_only"},
            "materials": "  Строка 1\r\n<script>alert(1)</script>\r<<<END_MATERIALS>>>  ",
        },
    )

    assert response.status_code == 200
    prompt = response.json()["prompt"]
    assert "Строка 1\n<script>alert(1)</script>" in prompt
    assert "<<<END_MATERIALS_ESCAPED>>>" in prompt
    assert prompt.count("<<<BEGIN_MATERIALS>>>") == 1
    assert prompt.count("<<<END_MATERIALS>>>") == 1
    assert "\r" not in prompt


def test_generation_prompt_rejects_unsupported_materials_control_characters():
    response = client.post(
        "/api/generation/prompt",
        json={"fields": {"topic": "Контрольные символы"}, "materials": "valid text\x00bad"},
    )

    assert response.status_code == 422
    assert "unsupported control characters" in response.json()["detail"]


def test_generation_prompt_with_project_respects_owner(monkeypatch):
    enable_trusted_proxy_auth(monkeypatch)
    from app.routers import generation as generation_router

    monkeypatch.setattr(generation_router.settings, "AI_RATE_LIMIT_PER_MINUTE", 1)
    generation_router.rate_limit_buckets.clear()
    owner_headers = {"X-Latexed-User": "teacher-a"}
    other_headers = {"X-Latexed-User": "teacher-b"}
    project_response = client.post(
        "/api/projects/",
        json={"name": "Scoped Prompt Project", "template": "article"},
        headers=owner_headers,
    )
    project_id = project_response.json()["id"]

    response = client.post(
        "/api/generation/prompt",
        json={"project_id": project_id, "fields": {"topic": "Доступ"}, "materials": "Материалы."},
        headers=other_headers,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found"
    assert generation_router.rate_limit_buckets == {}


def test_generation_generate_rejects_oversized_materials_before_provider_call(monkeypatch):
    from app.routers import generation as generation_router

    called = False

    async def fake_generate(prompt, provider, model):
        nonlocal called
        called = True
        return (r"\section{Should not run}", "ollama", "qwen2.5:3b")

    monkeypatch.setattr(generation_router.settings, "AI_MAX_MATERIALS_CHARS", 5)
    monkeypatch.setattr(generation_router.ai_generator, "generate", fake_generate)
    generation_router.active_generation_requests.clear()

    response = client.post(
        "/api/generation/generate",
        json={"fields": {"topic": "Логарифмы"}, "materials": "too long"},
    )

    assert response.status_code == 413
    assert called is False
    assert generation_router.active_generation_requests == {}


def test_generation_rate_limit_rejects_excess_requests(monkeypatch):
    from app.routers import generation as generation_router

    monkeypatch.setattr(generation_router.settings, "AI_RATE_LIMIT_PER_MINUTE", 1)
    generation_router.rate_limit_buckets.clear()

    first_response = client.post(
        "/api/generation/prompt",
        json={"fields": {"topic": "Логарифмы"}},
    )
    second_response = client.post(
        "/api/generation/prompt",
        json={"fields": {"topic": "Логарифмы"}},
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 429
    assert second_response.headers["Retry-After"].isdigit()
    assert second_response.json()["detail"].startswith("AI rate limit exceeded. Try again in ")
    generation_router.rate_limit_buckets.clear()


def test_generation_generate_rejects_duplicate_in_flight_without_rate_limit_increment(monkeypatch):
    from app.config import settings
    from app.routers import generation as generation_router

    started = threading.Event()
    release = threading.Event()
    calls = 0

    async def fake_generate(prompt, provider, model):
        nonlocal calls
        calls += 1
        started.set()
        assert release.wait(timeout=5), "timed out waiting to release first generation request"
        return (
            "```latex\n"
            r"\section{Duplicate guard}Only one provider call"
            "\n```",
            "ollama",
            "qwen2.5:3b",
        )

    monkeypatch.setattr(settings, "AI_COMPILE_CHECK_ENABLED", False)
    monkeypatch.setattr(generation_router.ai_generator, "generate", fake_generate)
    generation_router.rate_limit_buckets.clear()
    generation_router.active_generation_requests.clear()

    payload = {
        "fields": {"topic": "Дубликаты", "content_source_mode": "materials_only"},
        "materials": "Пользовательские материалы должны отправляться только один раз.",
    }
    first_result = {}

    def send_first_request():
        first_result["response"] = client.post("/api/generation/generate", json=payload)

    thread = threading.Thread(target=send_first_request)
    thread.start()
    try:
        assert started.wait(timeout=5), "first generation request did not reach provider"

        duplicate_response = client.post("/api/generation/generate", json=payload)

        assert duplicate_response.status_code == 409
        assert duplicate_response.headers["Retry-After"] == str(
            generation_router.GENERATION_DUPLICATE_RETRY_AFTER_SECONDS
        )
        assert duplicate_response.json()["detail"] == (
            "AI generation is already running for the same input. Wait for the current request to finish."
        )
        assert calls == 1
        assert sum(len(bucket) for bucket in generation_router.rate_limit_buckets.values()) == 1
    finally:
        release.set()
        thread.join(timeout=5)
        generation_router.rate_limit_buckets.clear()
        generation_router.active_generation_requests.clear()

    assert not thread.is_alive()
    assert first_result["response"].status_code == 200
    assert calls == 1


def test_estimated_token_counter_splits_text_and_latex_commands():
    from app.schemas import GenerationTokenUsageResponse
    from app.services.token_counter import add_estimated_usage, estimate_token_count

    assert estimate_token_count(r"\section{Тема} x^2 + 1") == 10

    usage = add_estimated_usage(
        GenerationTokenUsageResponse(),
        input_text="Промпт один",
        output_text=r"\section{Ответ}",
    )

    assert usage.input_tokens == 2
    assert usage.output_tokens == 5
    assert usage.total_tokens == 7
    assert usage.source == "estimated"


def test_ai_generation_service_defaults_to_qwen25_3b_for_ollama(monkeypatch):
    from app.config import settings
    from app.services.ai_generation import AIGenerationService

    monkeypatch.setattr(settings, "AI_PROVIDER", "ollama")
    monkeypatch.setattr(settings, "OLLAMA_MODEL", "qwen2.5:3b")

    provider, model = AIGenerationService().resolve_provider_model()

    assert provider == "ollama"
    assert model == "qwen2.5:3b"


def test_generation_provider_status_uses_selected_provider_and_model(monkeypatch):
    from app.routers import generation as generation_router

    async def fake_status(provider, model):
        assert provider == "ollama"
        assert model == "qwen2.5:14b"
        return {
            "provider": "ollama",
            "model": "qwen2.5:14b",
            "available": True,
            "message": "Ollama is reachable.",
            "models": ["qwen2.5:14b"],
            "model_available": True,
        }

    monkeypatch.setattr(generation_router.ai_generator, "get_provider_status", fake_status)

    response = client.get("/api/generation/providers/status?provider=ollama&model=qwen2.5:14b")
    assert response.status_code == 200
    data = response.json()
    assert data["available"] is True
    assert data["model_available"] is True
    assert data["models"] == ["qwen2.5:14b"]


def test_generation_validate_rejects_markdown_and_missing_document_end():
    response = client.post(
        "/api/generation/validate",
        json={"latex_code": "```latex\n\\documentclass{article}\n\\begin{document}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False
    assert any("markdown" in error for error in data["errors"])
    assert any("\\end{document}" in error for error in data["errors"])


def test_generation_validate_rejects_enumitem_list_true_option():
    response = client.post(
        "/api/generation/validate",
        json={
            "latex_code": r"\documentclass{article}\usepackage[list=true]{enumitem}\begin{document}Text\end{document}"
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False
    assert any("list=true" in error and "enumitem" in error for error in data["errors"])


@pytest.mark.parametrize(
    "latex_code, expected_error",
    [
        (
            r"\documentclass{article}\begin{document}\write18{rm -rf /}\end{document}",
            r"\write18",
        ),
        (
            r"\documentclass{article}\begin{document}\openout1=file.tex\end{document}",
            r"\openout",
        ),
        (
            r"\documentclass{article}\begin{document}\input|cat /etc/passwd\end{document}",
            r"\input|",
        ),
        (
            r"\documentclass{article}\begin{document}\input{/etc/passwd}\end{document}",
            "пути",
        ),
        (
            r"\documentclass{article}\usepackage{graphicx}\begin{document}\includegraphics{https://example.com/a.png}\end{document}",
            r"\includegraphics",
        ),
    ],
)
def test_generation_validate_rejects_dangerous_latex_commands(latex_code, expected_error):
    response = client.post(
        "/api/generation/validate",
        json={"latex_code": latex_code},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False
    assert any(expected_error in error for error in data["errors"])


def test_generation_validate_accepts_minimal_document_with_warnings():
    response = client.post(
        "/api/generation/validate",
        json={"latex_code": r"\documentclass{article}\begin{document}Ok\end{document}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is True
    assert data["warnings"]


def test_generation_generate_wraps_provider_body_with_fixed_preamble(monkeypatch):
    from app.routers import generation as generation_router

    async def fake_generate(prompt, provider, model):
        assert "Показательные уравнения" in prompt
        assert "Михаил Романов" in prompt
        assert provider == "ollama"
        assert model == "qwen2.5:14b"
        return (
            "```latex\n"
            r"\section{Сгенерировано}Generated"
            "\n```",
            "ollama",
            "qwen2.5:14b",
        )

    monkeypatch.setattr(generation_router.ai_generator, "generate", fake_generate)

    response = client.post(
        "/api/generation/generate",
        json={
            "provider": "ollama",
            "model": "qwen2.5:14b",
            "fields": {
                "topic": "Показательные уравнения",
                "student_name": "Михаил Романов",
            },
            "materials": "Решить уравнение 2^x = 8.",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["provider"] == "ollama"
    assert data["model"] == "qwen2.5:14b"
    assert data["latex_code"].startswith(r"\documentclass[a4paper,11pt]{article}")
    assert r"\usepackage{hyperref}" in data["latex_code"]
    assert r"\usepackage[most]{tcolorbox}" in data["latex_code"]
    assert r"\begin{document}" in data["latex_code"]
    assert r"\section{Сгенерировано}Generated" in data["latex_code"]
    assert data["latex_code"].endswith(r"\end{document}")
    assert data["raw_output"].startswith("```latex")
    assert data["validation"]["valid"] is True
    assert data["validation"]["warnings"] == []
    assert data["token_usage"]["input_tokens"] > 0
    assert data["token_usage"]["output_tokens"] > 0
    assert data["token_usage"]["total_tokens"] == data["token_usage"]["input_tokens"] + data["token_usage"]["output_tokens"]
    assert data["token_usage"]["source"] == "estimated"


def test_generation_history_records_success_and_supports_project_and_item_routes(monkeypatch):
    from app.routers import generation as generation_router
    from app.config import settings

    async def fake_generate(prompt, provider, model):
        return (
            "```latex\n"
            r"\section{History}Generated history body"
            "\n```",
            "ollama",
            "qwen2.5:3b",
        )

    monkeypatch.setattr(settings, "AI_COMPILE_CHECK_ENABLED", False)
    monkeypatch.setattr(generation_router.ai_generator, "generate", fake_generate)

    project_response = client.post(
        "/api/projects/",
        json={"name": "Generation History Project", "template": "article"},
    )
    project_id = project_response.json()["id"]

    response = client.post(
        "/api/generation/generate",
        json={"project_id": project_id, "fields": {"topic": "История генерации"}, "materials": "Материал."},
    )

    assert response.status_code == 200
    history_response = client.get(f"/api/generation/history/project/{project_id}")
    assert history_response.status_code == 200
    history = history_response.json()
    assert len(history) == 1
    item = history[0]
    assert item["project_id"] == project_id
    assert item["provider"] == "ollama"
    assert item["model"] == "qwen2.5:3b"
    assert item["status"] == "success"
    assert item["fields"]["topic"] == "История генерации"
    assert item["prompt_hash"]
    assert item["raw_output_hash"]
    assert item["latex_code_hash"]
    assert item["latex_code_preview"].startswith(r"\documentclass")
    assert item["compile_check"]["skipped_reason"] == "AI compile check is disabled."
    assert item["validation"]["valid"] is True
    assert item["input_tokens"] > 0
    assert item["output_tokens"] > 0
    assert item["total_tokens"] == item["input_tokens"] + item["output_tokens"]
    assert item["token_count_source"] == "estimated"
    assert "raw_output" not in item
    assert "prompt" not in item

    item_response = client.get(f"/api/generation/history/item/{item['id']}")
    assert item_response.status_code == 200
    assert item_response.json()["id"] == item["id"]


def test_generation_history_and_job_reads_respect_project_owner(monkeypatch):
    enable_trusted_proxy_auth(monkeypatch)
    from app.config import settings
    from app.routers import generation as generation_router

    async def fake_generate(prompt, provider, model):
        return (
            "```latex\n"
            r"\section{Scoped}Owner-only generation result"
            "\n```",
            "ollama",
            "qwen2.5:3b",
        )

    monkeypatch.setattr(settings, "AI_COMPILE_CHECK_ENABLED", False)
    monkeypatch.setattr(generation_router.ai_generator, "generate", fake_generate)
    owner_headers = {"X-Latexed-User": "teacher-a"}
    other_headers = {"X-Latexed-User": "teacher-b"}
    project_response = client.post(
        "/api/projects/",
        json={"name": "Scoped Generation Project", "template": "article"},
        headers=owner_headers,
    )
    project_id = project_response.json()["id"]

    generate_response = client.post(
        "/api/generation/generate",
        json={"project_id": project_id, "fields": {"topic": "История"}, "materials": "Материал."},
        headers=owner_headers,
    )
    assert generate_response.status_code == 200
    history_item = client.get(f"/api/generation/history/project/{project_id}", headers=owner_headers).json()[0]

    job_response = client.post(
        "/api/generation/jobs",
        json={"project_id": project_id, "fields": {"topic": "Job"}, "materials": "Материал."},
        headers=owner_headers,
    )
    assert job_response.status_code == 202
    job_id = job_response.json()["id"]

    assert client.get(f"/api/generation/history/project/{project_id}", headers=other_headers).status_code == 404
    assert client.get(f"/api/generation/history/item/{history_item['id']}", headers=other_headers).status_code == 404
    assert client.get(f"/api/generation/jobs/{job_id}", headers=other_headers).status_code == 404


def test_generation_job_create_runs_and_persists_completed_result(monkeypatch):
    from app.config import settings
    from app.routers import generation as generation_router

    async def fake_generate(prompt, provider, model):
        return (
            "```latex\n"
            r"\section{Job}Persisted generation result"
            "\n```",
            "ollama",
            "qwen2.5:3b",
        )

    monkeypatch.setattr(settings, "AI_COMPILE_CHECK_ENABLED", False)
    monkeypatch.setattr(generation_router.ai_generator, "generate", fake_generate)

    response = client.post(
        "/api/generation/jobs",
        json={"fields": {"topic": "Job API"}, "materials": "Материалы для job."},
    )

    assert response.status_code == 202
    job = response.json()
    assert job["status"] == "completed"
    assert job["stage"] == "completed"
    assert job["attempts"] == 1
    assert job["request_hash"]
    assert job["prompt_hash"]
    assert job["queue_wait_seconds"] is not None
    assert job["run_duration_seconds"] is not None
    assert job["total_duration_seconds"] is not None
    assert job["result"]["status"] == "success"
    assert "Persisted generation result" in job["result"]["latex_code"]

    status_response = client.get(f"/api/generation/jobs/{job['id']}")
    assert status_response.status_code == 200
    assert status_response.json()["id"] == job["id"]
    assert status_response.json()["result"]["latex_code"] == job["result"]["latex_code"]


def test_generation_job_idempotency_key_replays_existing_job(monkeypatch):
    from app.config import settings
    from app.routers import generation as generation_router

    calls = 0

    async def fake_generate(prompt, provider, model):
        nonlocal calls
        calls += 1
        return (
            "```latex\n"
            r"\section{Idempotent}Single provider call"
            "\n```",
            "ollama",
            "qwen2.5:3b",
        )

    monkeypatch.setattr(settings, "AI_COMPILE_CHECK_ENABLED", False)
    monkeypatch.setattr(generation_router.ai_generator, "generate", fake_generate)
    generation_router.rate_limit_buckets.clear()
    payload = {"fields": {"topic": "Idempotency"}, "materials": "Материал."}
    headers = {"Idempotency-Key": "generation-job-retry-1"}

    first_response = client.post("/api/generation/jobs", json=payload, headers=headers)
    second_response = client.post("/api/generation/jobs", json=payload, headers=headers)

    assert first_response.status_code == 202
    assert second_response.status_code == 202
    assert second_response.json()["id"] == first_response.json()["id"]
    assert second_response.json()["idempotency_key"] == "generation-job-retry-1"
    assert calls == 1


def test_generation_job_idempotency_key_rejects_different_payload(monkeypatch):
    from app.config import settings
    from app.routers import generation as generation_router

    async def fake_generate(prompt, provider, model):
        return (
            "```latex\n"
            r"\section{Idempotent}Original"
            "\n```",
            "ollama",
            "qwen2.5:3b",
        )

    monkeypatch.setattr(settings, "AI_COMPILE_CHECK_ENABLED", False)
    monkeypatch.setattr(generation_router.ai_generator, "generate", fake_generate)
    generation_router.rate_limit_buckets.clear()
    headers = {"Idempotency-Key": "generation-job-retry-2"}

    first_response = client.post(
        "/api/generation/jobs",
        json={"fields": {"topic": "Первый"}, "materials": "Материал."},
        headers=headers,
    )
    second_response = client.post(
        "/api/generation/jobs",
        json={"fields": {"topic": "Другой"}, "materials": "Материал."},
        headers=headers,
    )

    assert first_response.status_code == 202
    assert second_response.status_code == 409
    assert second_response.json()["detail"] == "Idempotency key was already used for a different generation request."


def test_generation_job_background_mode_returns_queued_then_completes(monkeypatch):
    from app.config import settings
    from app.routers import generation as generation_router

    async def fake_generate(prompt, provider, model):
        return (
            "```latex\n"
            r"\section{Background}Completed from background task"
            "\n```",
            "ollama",
            "qwen2.5:3b",
        )

    monkeypatch.setattr(settings, "AI_GENERATION_JOB_EXECUTION_MODE", "background")
    monkeypatch.setattr(settings, "AI_COMPILE_CHECK_ENABLED", False)
    monkeypatch.setattr(generation_router.ai_generator, "generate", fake_generate)
    monkeypatch.setattr(generation_router, "SessionLocal", SessionTesting)
    generation_router.rate_limit_buckets.clear()

    response = client.post(
        "/api/generation/jobs",
        json={"fields": {"topic": "Background"}, "materials": "Материал."},
    )

    assert response.status_code == 202
    job = response.json()
    assert job["status"] == "queued"
    assert job["stage"] == "queued"

    status_response = client.get(f"/api/generation/jobs/{job['id']}")
    assert status_response.status_code == 200
    completed_job = status_response.json()
    assert completed_job["status"] == "completed"
    assert "Completed from background task" in completed_job["result"]["latex_code"]


def test_generation_job_external_mode_leaves_job_queued_for_worker(monkeypatch):
    from app.config import settings
    from app.routers import generation as generation_router

    calls = 0

    async def fake_generate(prompt, provider, model):
        nonlocal calls
        calls += 1
        return (
            "```latex\n"
            r"\section{External}Should not run in request"
            "\n```",
            "ollama",
            "qwen2.5:3b",
        )

    monkeypatch.setattr(settings, "AI_GENERATION_JOB_EXECUTION_MODE", "external")
    monkeypatch.setattr(generation_router.ai_generator, "generate", fake_generate)
    generation_router.rate_limit_buckets.clear()

    response = client.post(
        "/api/generation/jobs",
        json={"fields": {"topic": "External"}, "materials": "Материал."},
    )

    assert response.status_code == 202
    job = response.json()
    assert job["status"] == "queued"
    assert job["stage"] == "queued"
    assert job["queue_wait_seconds"] is None
    assert calls == 0

    status_response = client.get(f"/api/generation/jobs/{job['id']}")
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "queued"


def test_generation_worker_runs_queued_external_job(monkeypatch):
    import asyncio
    from app.config import settings
    from app.routers import generation as generation_router
    from app.services import generation_job_worker

    async def fake_generate(prompt, provider, model):
        return (
            "```latex\n"
            r"\section{Worker}Processed queued job"
            "\n```",
            "ollama",
            "qwen2.5:3b",
        )

    monkeypatch.setattr(settings, "AI_GENERATION_JOB_EXECUTION_MODE", "external")
    monkeypatch.setattr(settings, "AI_COMPILE_CHECK_ENABLED", False)
    monkeypatch.setattr(generation_router.ai_generator, "generate", fake_generate)
    monkeypatch.setattr(generation_job_worker.ai_generator, "generate", fake_generate)
    generation_router.rate_limit_buckets.clear()

    create_response = client.post(
        "/api/generation/jobs",
        json={"fields": {"topic": "Worker"}, "materials": "Материал."},
    )
    assert create_response.status_code == 202
    job = create_response.json()
    assert job["status"] == "queued"

    db = SessionTesting()
    try:
        processed = asyncio.run(generation_job_worker.run_generation_job_once(db=db, job_id=job["id"]))
    finally:
        db.close()

    assert processed is not None
    assert processed.status == "completed"

    status_response = client.get(f"/api/generation/jobs/{job['id']}")
    assert status_response.status_code == 200
    completed = status_response.json()
    assert completed["status"] == "completed"
    assert completed["run_duration_seconds"] is not None
    assert "Processed queued job" in completed["result"]["latex_code"]


def test_generation_worker_recovers_stale_running_job(monkeypatch):
    from datetime import timedelta
    from app.config import settings
    from app.routers import generation as generation_router
    from app.services import generation_job_worker
    from app.time_utils import utc_now

    async def fake_generate(prompt, provider, model):
        return (
            "```latex\n"
            r"\section{Stale}Recovered job"
            "\n```",
            "ollama",
            "qwen2.5:3b",
        )

    monkeypatch.setattr(settings, "AI_GENERATION_JOB_EXECUTION_MODE", "external")
    monkeypatch.setattr(generation_router.ai_generator, "generate", fake_generate)
    generation_router.rate_limit_buckets.clear()

    create_response = client.post(
        "/api/generation/jobs",
        json={"fields": {"topic": "Stale"}, "materials": "Материал."},
    )
    assert create_response.status_code == 202
    job_id = create_response.json()["id"]

    db = SessionTesting()
    try:
        job = generation_job_worker.generation_job_service.get_job(db, job_id=job_id)
        stale_time = utc_now() - timedelta(seconds=300)
        job.status = "running"
        job.stage = "generating"
        job.started_at = stale_time
        job.updated_at = stale_time
        db.add(job)
        db.commit()

        recovered = generation_job_worker.recover_stale_generation_jobs(
            db=db,
            stale_after_seconds=60,
        )
        recovered_job = generation_job_worker.generation_job_service.get_job(db, job_id=job_id)
        recovered_state = {
            "status": recovered_job.status,
            "stage": recovered_job.stage,
            "started_at": recovered_job.started_at,
            "error_message": recovered_job.error_message,
        }
    finally:
        db.close()

    assert recovered == 1
    assert recovered_state["status"] == "queued"
    assert recovered_state["stage"] == "queued"
    assert recovered_state["started_at"] is None
    assert recovered_state["error_message"] == "Recovered from stale running state; queued for worker retry."


def test_generation_operator_status_and_recover_stale_are_owner_scoped(monkeypatch):
    enable_trusted_proxy_auth(monkeypatch)
    from datetime import timedelta
    from app.config import settings
    from app.routers import generation as generation_router
    from app.services.generation_job_worker import generation_job_service
    from app.time_utils import utc_now

    async def fake_generate(prompt, provider, model):
        return (
            "```latex\n"
            r"\section{Operator}Queued"
            "\n```",
            "ollama",
            "qwen2.5:3b",
        )

    monkeypatch.setattr(settings, "AI_GENERATION_JOB_EXECUTION_MODE", "external")
    monkeypatch.setattr(settings, "AI_GENERATION_JOB_STALE_AFTER_SECONDS", 60)
    monkeypatch.setattr(generation_router.ai_generator, "generate", fake_generate)
    generation_router.rate_limit_buckets.clear()
    owner_headers = {"X-Latexed-User": "operator-a"}
    other_headers = {"X-Latexed-User": "operator-b"}

    response = client.post(
        "/api/generation/jobs",
        json={"fields": {"topic": "Operator"}, "materials": "Материал."},
        headers=owner_headers,
    )
    assert response.status_code == 202
    job_id = response.json()["id"]

    db = SessionTesting()
    try:
        job = generation_job_service.get_job(db, job_id=job_id)
        stale_time = utc_now() - timedelta(seconds=300)
        job.status = "running"
        job.stage = "generating"
        job.updated_at = stale_time
        db.add(job)
        db.commit()
    finally:
        db.close()

    status_response = client.get("/api/generation/jobs/operator/status", headers=owner_headers)
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["counts"]["running"] == 1
    assert status_payload["backlog"] == 1
    assert status_payload["stale_running"] == 1
    assert [sample["id"] for sample in status_payload["stale_samples"]] == [job_id]

    other_status_response = client.get("/api/generation/jobs/operator/status", headers=other_headers)
    assert other_status_response.status_code == 200
    assert other_status_response.json()["backlog"] == 0

    recover_response = client.post(
        "/api/generation/jobs/operator/recover-stale",
        json={"stale_after_seconds": 60},
        headers=owner_headers,
    )
    assert recover_response.status_code == 200
    recover_payload = recover_response.json()
    assert recover_payload["recovered_count"] == 1
    assert recover_payload["recovered_job_ids"] == [job_id]

    recovered_job = client.get(f"/api/generation/jobs/{job_id}", headers=owner_headers).json()
    assert recovered_job["status"] == "queued"
    assert recovered_job["error_message"] == "Recovered from stale running state; queued for worker retry."


def test_generation_job_cancel_queued_background_job(monkeypatch):
    from app.config import settings
    from app.routers import generation as generation_router

    async def noop_background_runner(job_id):
        return None

    monkeypatch.setattr(settings, "AI_GENERATION_JOB_EXECUTION_MODE", "background")
    monkeypatch.setattr(generation_router, "run_generation_job_background", noop_background_runner)
    generation_router.rate_limit_buckets.clear()

    create_response = client.post(
        "/api/generation/jobs",
        json={"fields": {"topic": "Cancel"}, "materials": "Материал."},
    )

    assert create_response.status_code == 202
    job = create_response.json()
    assert job["status"] == "queued"

    cancel_response = client.post(f"/api/generation/jobs/{job['id']}/cancel")

    assert cancel_response.status_code == 200
    canceled = cancel_response.json()
    assert canceled["status"] == "canceled"
    assert canceled["stage"] == "canceled"
    assert canceled["error_message"] == "Generation job was canceled by user request."


def test_generation_job_timeout_marks_job_failed(monkeypatch):
    import asyncio
    from app.config import settings
    from app.routers import generation as generation_router

    async def slow_generate(prompt, provider, model):
        await asyncio.sleep(0.05)
        return (
            "```latex\n"
            r"\section{Too slow}"
            "\n```",
            "ollama",
            "qwen2.5:3b",
        )

    monkeypatch.setattr(settings, "AI_GENERATION_JOB_EXECUTION_MODE", "inline")
    monkeypatch.setattr(settings, "AI_GENERATION_JOB_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(settings, "AI_COMPILE_CHECK_ENABLED", False)
    monkeypatch.setattr(generation_router.ai_generator, "generate", slow_generate)
    generation_router.rate_limit_buckets.clear()

    response = client.post(
        "/api/generation/jobs",
        json={"fields": {"topic": "Timeout"}, "materials": "Материал."},
    )

    assert response.status_code == 202
    job = response.json()
    assert job["status"] == "failed"
    assert job["stage"] == "failed"
    assert job["error_message"] == "AI generation job timed out."


def test_generation_job_rejects_invalid_idempotency_key():
    response = client.post(
        "/api/generation/jobs",
        json={"fields": {"topic": "Bad key"}, "materials": "Материал."},
        headers={"Idempotency-Key": "bad key with spaces"},
    )

    assert response.status_code == 400
    assert "Invalid idempotency key" in response.json()["detail"]


def test_generation_job_persists_provider_failure(monkeypatch):
    from app.routers import generation as generation_router
    from app.services.ai_generation import AIGenerationError

    async def fake_generate(prompt, provider, model):
        raise AIGenerationError("Provider unavailable")

    monkeypatch.setattr(generation_router.ai_generator, "generate", fake_generate)

    response = client.post(
        "/api/generation/jobs",
        json={"fields": {"topic": "Job failure"}, "materials": "Материалы."},
    )

    assert response.status_code == 202
    job = response.json()
    assert job["status"] == "failed"
    assert job["stage"] == "failed"
    assert job["attempts"] == 1
    assert job["result"] is None
    assert job["error_message"] == "AI provider request failed. Check backend logs or provider configuration."

    status_response = client.get(f"/api/generation/jobs/{job['id']}")
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "failed"


def test_generation_jobs_can_be_listed_by_status_project_and_owner(monkeypatch):
    enable_trusted_proxy_auth(monkeypatch)
    from app.config import settings
    from app.routers import generation as generation_router

    async def fake_generate(prompt, provider, model):
        return (
            "```latex\n"
            r"\section{List}Job list"
            "\n```",
            "ollama",
            "qwen2.5:3b",
        )

    monkeypatch.setattr(settings, "AI_COMPILE_CHECK_ENABLED", False)
    monkeypatch.setattr(generation_router.ai_generator, "generate", fake_generate)
    owner_headers = {"X-Latexed-User": "teacher-a"}
    other_headers = {"X-Latexed-User": "teacher-b"}
    project_response = client.post(
        "/api/projects/",
        json={"name": "Job List Project", "template": "article"},
        headers=owner_headers,
    )
    project_id = project_response.json()["id"]
    job_response = client.post(
        "/api/generation/jobs",
        json={"project_id": project_id, "fields": {"topic": "List"}, "materials": "Материал."},
        headers=owner_headers,
    )
    assert job_response.status_code == 202
    job_id = job_response.json()["id"]

    list_response = client.get(
        f"/api/generation/jobs?project_id={project_id}&status=completed",
        headers=owner_headers,
    )
    assert list_response.status_code == 200
    assert [job["id"] for job in list_response.json()] == [job_id]

    other_response = client.get(
        f"/api/generation/jobs?project_id={project_id}&status=completed",
        headers=other_headers,
    )
    assert other_response.status_code == 404


def test_generation_failed_job_can_be_retried(monkeypatch):
    from app.config import settings
    from app.routers import generation as generation_router
    from app.services.ai_generation import AIGenerationError

    async def failing_generate(prompt, provider, model):
        raise AIGenerationError("Temporary provider failure")

    monkeypatch.setattr(settings, "AI_COMPILE_CHECK_ENABLED", False)
    monkeypatch.setattr(generation_router.ai_generator, "generate", failing_generate)
    generation_router.rate_limit_buckets.clear()

    create_response = client.post(
        "/api/generation/jobs",
        json={"fields": {"topic": "Retry failed job"}, "materials": "Материал."},
    )
    assert create_response.status_code == 202
    failed_job = create_response.json()
    assert failed_job["status"] == "failed"

    async def successful_generate(prompt, provider, model):
        return (
            "```latex\n"
            r"\section{Retry}Recovered"
            "\n```",
            "ollama",
            "qwen2.5:3b",
        )

    monkeypatch.setattr(generation_router.ai_generator, "generate", successful_generate)
    retry_response = client.post(f"/api/generation/jobs/{failed_job['id']}/retry")

    assert retry_response.status_code == 200
    retried_job = retry_response.json()
    assert retried_job["id"] == failed_job["id"]
    assert retried_job["status"] == "completed"
    assert retried_job["attempts"] == 2
    assert "Recovered" in retried_job["result"]["latex_code"]


def test_generation_completed_job_retry_is_rejected(monkeypatch):
    from app.config import settings
    from app.routers import generation as generation_router

    async def fake_generate(prompt, provider, model):
        return (
            "```latex\n"
            r"\section{Done}"
            "\n```",
            "ollama",
            "qwen2.5:3b",
        )

    monkeypatch.setattr(settings, "AI_COMPILE_CHECK_ENABLED", False)
    monkeypatch.setattr(generation_router.ai_generator, "generate", fake_generate)

    create_response = client.post(
        "/api/generation/jobs",
        json={"fields": {"topic": "Already done"}, "materials": "Материал."},
    )
    assert create_response.status_code == 202
    job = create_response.json()
    assert job["status"] == "completed"

    retry_response = client.post(f"/api/generation/jobs/{job['id']}/retry")

    assert retry_response.status_code == 409
    assert retry_response.json()["detail"] == "Only failed or canceled generation jobs can be retried."


def test_generation_job_not_found_returns_404():
    response = client.get("/api/generation/jobs/missing")

    assert response.status_code == 404
    assert "Generation job missing not found" in response.json()["detail"]


def test_generation_history_records_provider_failure(monkeypatch):
    enable_trusted_proxy_auth(monkeypatch)
    from app.config import settings
    from app.routers import generation as generation_router

    async def fake_generate(prompt, provider, model):
        return (
            "```latex\n"
            r"\section{Scoped}Owner-only generation result"
            "\n```",
            "ollama",
            "qwen2.5:3b",
        )

    monkeypatch.setattr(settings, "AI_COMPILE_CHECK_ENABLED", False)
    monkeypatch.setattr(generation_router.ai_generator, "generate", fake_generate)
    owner_headers = {"X-Latexed-User": "teacher-a"}
    other_headers = {"X-Latexed-User": "teacher-b"}
    project_response = client.post(
        "/api/projects/",
        json={"name": "Scoped Generation Project", "template": "article"},
        headers=owner_headers,
    )
    project_id = project_response.json()["id"]

    generate_response = client.post(
        "/api/generation/generate",
        json={"project_id": project_id, "fields": {"topic": "История"}, "materials": "Материал."},
        headers=owner_headers,
    )
    assert generate_response.status_code == 200
    history_item = client.get(f"/api/generation/history/project/{project_id}", headers=owner_headers).json()[0]

    job_response = client.post(
        "/api/generation/jobs",
        json={"project_id": project_id, "fields": {"topic": "Job"}, "materials": "Материал."},
        headers=owner_headers,
    )
    assert job_response.status_code == 202
    job_id = job_response.json()["id"]

    assert client.get(f"/api/generation/history/project/{project_id}", headers=other_headers).status_code == 404
    assert client.get(f"/api/generation/history/item/{history_item['id']}", headers=other_headers).status_code == 404
    assert client.get(f"/api/generation/jobs/{job_id}", headers=other_headers).status_code == 404


def test_generation_job_create_runs_and_persists_completed_result(monkeypatch):
    from app.config import settings
    from app.routers import generation as generation_router

    async def fake_generate(prompt, provider, model):
        return (
            "```latex\n"
            r"\section{Job}Persisted generation result"
            "\n```",
            "ollama",
            "qwen2.5:3b",
        )

    monkeypatch.setattr(settings, "AI_COMPILE_CHECK_ENABLED", False)
    monkeypatch.setattr(generation_router.ai_generator, "generate", fake_generate)

    response = client.post(
        "/api/generation/jobs",
        json={"fields": {"topic": "Job API"}, "materials": "Материалы для job."},
    )

    assert response.status_code == 202
    job = response.json()
    assert job["status"] == "completed"
    assert job["stage"] == "completed"
    assert job["attempts"] == 1
    assert job["request_hash"]
    assert job["prompt_hash"]
    assert job["queue_wait_seconds"] is not None
    assert job["run_duration_seconds"] is not None
    assert job["total_duration_seconds"] is not None
    assert job["result"]["status"] == "success"
    assert "Persisted generation result" in job["result"]["latex_code"]

    status_response = client.get(f"/api/generation/jobs/{job['id']}")
    assert status_response.status_code == 200
    assert status_response.json()["id"] == job["id"]
    assert status_response.json()["result"]["latex_code"] == job["result"]["latex_code"]


def test_generation_job_idempotency_key_replays_existing_job(monkeypatch):
    from app.config import settings
    from app.routers import generation as generation_router

    calls = 0

    async def fake_generate(prompt, provider, model):
        nonlocal calls
        calls += 1
        return (
            "```latex\n"
            r"\section{Idempotent}Single provider call"
            "\n```",
            "ollama",
            "qwen2.5:3b",
        )

    monkeypatch.setattr(settings, "AI_COMPILE_CHECK_ENABLED", False)
    monkeypatch.setattr(generation_router.ai_generator, "generate", fake_generate)
    generation_router.rate_limit_buckets.clear()
    payload = {"fields": {"topic": "Idempotency"}, "materials": "Материал."}
    headers = {"Idempotency-Key": "generation-job-retry-1"}

    monkeypatch.setattr(settings, "AI_COMPILE_CHECK_ENABLED", True)
    monkeypatch.setattr(settings, "AI_REPAIR_ATTEMPTS", 1)
    from app.services import generation_orchestrator as orchestrator_module

    monkeypatch.setattr(orchestrator_module.shutil, "which", lambda compiler: "/usr/bin/pdflatex")
    monkeypatch.setattr(generation_router.ai_generator, "generate", fake_generate)
    generation_router.rate_limit_buckets.clear()
    headers = {"Idempotency-Key": "generation-job-retry-2"}

    first_response = client.post(
        "/api/generation/jobs",
        json={"fields": {"topic": "Первый"}, "materials": "Материал."},
        headers=headers,
    )
    second_response = client.post(
        "/api/generation/jobs",
        json={"fields": {"topic": "Другой"}, "materials": "Материал."},
        headers=headers,
    )

    assert first_response.status_code == 202
    assert second_response.status_code == 409
    assert second_response.json()["detail"] == "Idempotency key was already used for a different generation request."


def test_generation_job_background_mode_returns_queued_then_completes(monkeypatch):
    from app.config import settings
    from app.routers import generation as generation_router

    async def fake_generate(prompt, provider, model):
        return (
            "```latex\n"
            r"\section{Background}Completed from background task"
            "\n```",
            "ollama",
            "qwen2.5:3b",
        )

    monkeypatch.setattr(settings, "AI_GENERATION_JOB_EXECUTION_MODE", "background")
    monkeypatch.setattr(settings, "AI_COMPILE_CHECK_ENABLED", False)
    monkeypatch.setattr(generation_router.ai_generator, "generate", fake_generate)
    monkeypatch.setattr(generation_router, "SessionLocal", SessionTesting)
    generation_router.rate_limit_buckets.clear()

    response = client.post(
        "/api/generation/jobs",
        json={"fields": {"topic": "Background"}, "materials": "Материал."},
    )

    assert response.status_code == 202
    job = response.json()
    assert job["status"] == "queued"
    assert job["stage"] == "queued"

    status_response = client.get(f"/api/generation/jobs/{job['id']}")
    assert status_response.status_code == 200
    completed_job = status_response.json()
    assert completed_job["status"] == "completed"
    assert "Completed from background task" in completed_job["result"]["latex_code"]


def test_generation_job_external_mode_leaves_job_queued_for_worker(monkeypatch):
    from app.config import settings
    from app.routers import generation as generation_router

    calls = 0

    async def fake_generate(prompt, provider, model):
        nonlocal calls
        calls += 1
        return (
            "```latex\n"
            r"\section{External}Should not run in request"
            "\n```",
            "ollama",
            "qwen2.5:3b",
        )

    monkeypatch.setattr(settings, "AI_GENERATION_JOB_EXECUTION_MODE", "external")
    monkeypatch.setattr(generation_router.ai_generator, "generate", fake_generate)
    generation_router.rate_limit_buckets.clear()

    response = client.post(
        "/api/generation/jobs",
        json={"fields": {"topic": "External mode"}, "materials": "Материал."},
    )

    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "queued"
    assert data["stage"] == "queued"
    assert data["attempts"] == 0
    assert data["result"] is None
    assert calls == 0


def test_generation_generate_timeout_returns_actionable_message(monkeypatch):
    from app.routers import generation as generation_router
    from app.services.ai_generation import AIGenerationError

    async def fake_generate(prompt, provider, model):
        raise AIGenerationError(
            "Ollama generation timed out after 120 seconds. Check that Ollama is running, the model is pulled and loaded, or increase AI_GENERATION_TIMEOUT.",
            status_code=504,
        )

    monkeypatch.setattr(generation_router.ai_generator, "generate", fake_generate)

    response = client.post(
        "/api/generation/generate",
        json={
            "provider": "ollama",
            "model": "qwen2.5:14b",
            "fields": {"topic": "Логарифмы"},
            "materials": "Решить log_2(x)=3.",
        },
    )
    assert response.status_code == 504
    assert "timed out after 120 seconds" in response.json()["detail"]
    assert "AI_GENERATION_TIMEOUT" in response.json()["detail"]


def test_generation_generate_provider_error_returns_bad_gateway(monkeypatch):
    from app.routers import generation as generation_router
    from app.services.ai_generation import AIGenerationError

    async def fake_generate(prompt, provider, model):
        raise AIGenerationError("Provider unavailable")

    monkeypatch.setattr(generation_router.ai_generator, "generate", fake_generate)

    response = client.post(
        "/api/generation/generate",
        json={
            "provider": "ollama",
            "fields": {"topic": "Логарифмы"},
            "materials": "Решить log_2(x)=3.",
        },
    )
    assert response.status_code == 502
    assert response.json()["detail"] == "AI provider request failed. Check backend logs or provider configuration."


def test_openapi_schema():
    response = client.get("/api/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert "openapi" in schema
    assert "paths" in schema
