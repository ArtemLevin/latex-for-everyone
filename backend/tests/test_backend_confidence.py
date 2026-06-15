"""Regression checks for backend timestamp policy and warning cleanup."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.time_utils import utc_now


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_APP = REPO_ROOT / "backend" / "app"


def test_utc_now_returns_timezone_aware_utc_datetime():
    now = utc_now()

    assert now.tzinfo is UTC
    assert now.utcoffset().total_seconds() == 0


def test_backend_app_uses_timestamp_helper_directly():
    offenders = []
    for path in BACKEND_APP.rglob("*.py"):
        if path.name == "time_utils.py":
            continue
        text = path.read_text(encoding="utf-8")
        if "datetime." + "utc" + "now" in text or "utc" + "now()" in text:
            offenders.append(str(path.relative_to(REPO_ROOT)))

    assert offenders == []


@pytest.fixture()
def isolated_client(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'timestamps.db'}", connect_args={"check_same_thread": False})
    SessionTesting = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = SessionTesting()
        try:
            yield db
        finally:
            db.close()

    original_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            yield client
    finally:
        if original_override is not None:
            app.dependency_overrides[get_db] = original_override
        else:
            app.dependency_overrides.pop(get_db, None)
        Base.metadata.drop_all(bind=engine)


def test_project_and_file_timestamp_responses_remain_parseable(isolated_client):
    project_response = isolated_client.post("/api/projects/", json={"name": "Timestamp Project"})
    assert project_response.status_code == 201
    project = project_response.json()

    files_response = isolated_client.get(f"/api/files/project/{project['id']}")
    assert files_response.status_code == 200
    file = files_response.json()[0]

    for payload in [project, file]:
        assert datetime.fromisoformat(payload["created_at"])
        assert datetime.fromisoformat(payload["updated_at"])


def test_latex_compiler_uses_uuid_compile_work_directories():
    source = (REPO_ROOT / "backend" / "app" / "services" / "latex_compiler.py").read_text(encoding="utf-8")

    assert "compile_{uuid.uuid4().hex}" in source
    assert "os.getpid()" not in source
    assert "int(time.time())" not in source


def test_generation_router_delegates_provider_orchestration_to_service():
    router_source = (BACKEND_APP / "routers" / "generation.py").read_text(encoding="utf-8")
    service_source = (BACKEND_APP / "services" / "generation_orchestrator.py").read_text(encoding="utf-8")

    assert "generation_orchestrator = GenerationOrchestrator(" in router_source
    assert "await generation_orchestrator.generate(" in router_source
    assert "async def _compile_check_and_repair" in service_source
    assert "async def compile_check_and_repair" not in router_source
    assert "raw_output, provider, model = await ai_generator.generate" not in router_source
