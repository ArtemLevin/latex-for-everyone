from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.models import CompileJob, File, Project
from app.services.compile_jobs import CompileJobService
from app.services.compile_runners.docker_sandbox import DockerSandboxCompileRunner

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_compile_sandbox_latexed.db"
engine_test = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionTesting = sessionmaker(autocommit=False, autoflush=False, bind=engine_test)


def override_get_db():
    db = SessionTesting()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup_db(monkeypatch):
    previous_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.drop_all(bind=engine_test)
    Base.metadata.create_all(bind=engine_test)
    monkeypatch.setattr(settings, "AUTH_MODE", "local")
    monkeypatch.setattr(settings, "LOCAL_USER_ID", "compile-owner")
    monkeypatch.setattr(settings, "COMPILE_EXECUTION_MODE", "local_subprocess")
    yield
    Base.metadata.drop_all(bind=engine_test)
    if previous_override is not None:
        app.dependency_overrides[get_db] = previous_override
    else:
        app.dependency_overrides.pop(get_db, None)


client = TestClient(app)


def create_project() -> str:
    db = SessionTesting()
    try:
        project = Project(name="Sandboxed", owner_id="compile-owner")
        db.add(project)
        db.flush()
        db.add(
            File(
                project_id=project.id,
                name="main.tex",
                content="\\documentclass{article}\\begin{document}Hi\\end{document}",
                is_main=True,
            )
        )
        db.commit()
        return project.id
    finally:
        db.close()


def test_compile_jobs_endpoint_returns_202_without_running_pdflatex(monkeypatch):
    project_id = create_project()

    def fail_if_called(*args, **kwargs):
        raise AssertionError("pdflatex must not run in POST /api/compile/jobs")

    monkeypatch.setattr("app.routers.compile.run_latex_compile_checked", fail_if_called)

    response = client.post("/api/compile/jobs", json={"project_id": project_id})

    assert response.status_code == 202
    assert response.headers["Location"].startswith("/api/compile/jobs/")
    payload = response.json()
    assert payload["status"] == "queued"
    assert payload["stage"] == "queued"
    assert payload["history_id"]


def test_compile_job_poll_is_owner_scoped(monkeypatch):
    project_id = create_project()
    created = client.post("/api/compile/jobs", json={"project_id": project_id})
    job_id = created.json()["id"]

    owner_get = client.get(f"/api/compile/jobs/{job_id}")
    monkeypatch.setattr(settings, "LOCAL_USER_ID", "other-owner")
    other_get = client.get(f"/api/compile/jobs/{job_id}")

    assert owner_get.status_code == 200
    assert other_get.status_code == 404


def test_compile_queue_claim_and_cancel_states():
    db = SessionTesting()
    try:
        service = CompileJobService()
        job = service.create_job(
            db,
            owner_id="owner",
            project_id=None,
            compile_history_id=None,
            main_file_name="main.tex",
            request_payload={"main_content": "x", "files": {}, "main_file_name": "main.tex"},
        )
        claimed = service.claim_next_job(db, worker_id="worker-1")
        assert claimed.id == job.id
        assert claimed.status == "running"
        assert claimed.worker_id == "worker-1"
        assert claimed.attempts == 1

        canceled = service.cancel_job(db, job=claimed)
        assert canceled.cancel_requested is True
    finally:
        db.close()


def test_docker_runner_uses_hardened_sandbox_flags(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "COMPILE_SANDBOX_IMAGE", "latexed-latex-sandbox:test")
    runner = DockerSandboxCompileRunner()

    command = runner.build_docker_command(
        input_dir=tmp_path / "input",
        output_dir=tmp_path / "out",
        main_filename="main.tex",
        container_name="compile_test",
    )
    joined = " ".join(command)

    assert "--network none" in joined
    assert "--user 10001:10001" in joined
    assert "--read-only" in command
    assert "--cap-drop ALL" in joined
    assert "--security-opt no-new-privileges:true" in joined
    assert "--memory 256m" in joined
    assert "--cpus 1.0" in joined
    assert "--pids-limit 128" in joined
    assert "openin_any=p" in joined
    assert "openout_any=p" in joined
    assert "shell_escape=f" in joined
    assert command[-2:] == ["latexed-latex-sandbox:test", "main.tex"]


def test_sandbox_compile_script_disables_shell_escape_and_sets_tex_policy():
    script = Path("docker/latex-sandbox/compile.sh").read_text()

    assert "-no-shell-escape" in script
    assert "openin_any" in script
    assert "openout_any" in script
    assert "shell_escape=f" in script
