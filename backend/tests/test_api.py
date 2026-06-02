"""
Tests for the Latexed API.
"""
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


def test_health_check():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


def test_root():
    response = client.get("/")
    assert response.status_code == 200


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


def test_list_templates():
    response = client.get("/api/templates/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0


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


def test_compile_history_project_and_item_routes(monkeypatch):
    from app.routers import compile as compile_router

    def fake_compile(main_content, files):
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
    assert response.content == b"%PDF-1.4 test pdf"


def test_compile_pdf_download_rejects_invalid_filename():
    response = client.get("/api/compile/download/not-a-pdf.txt")
    assert response.status_code == 400


def test_openapi_schema():
    response = client.get("/api/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert "openapi" in schema
    assert "paths" in schema
