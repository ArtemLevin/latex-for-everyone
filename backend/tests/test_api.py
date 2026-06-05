"""
Tests for the Latexed API.
"""
from pathlib import Path

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


def test_latex_compiler_adds_russian_babel_environment_hint():
    from app.services.latex_compiler import LatexCompiler

    log_text = """
! Package babel Error: Unknown option 'russian'. Either you misspelled it
(babel)                or the language definition file russian.ldf was not found.
"""
    errors = LatexCompiler()._extract_errors(log_text)

    assert "Unknown option 'russian'" in errors
    assert "texlive-lang-cyrillic" in errors


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
    frontend_html = Path(__file__).resolve().parents[2] / "frontend" / "main.html"
    content = frontend_html.read_text(encoding="utf-8")

    assert 'id="generationModal"' in content
    assert 'id="generationTopic"' in content
    assert 'id="generationMaterials"' in content
    assert "collectGenerationRequest" in content
    assert "generateLatexFromAi" in content
    assert "validateCurrentLatex" in content
    assert "checkGenerationProvider" in content
    assert 'id="generationInsertMode"' in content
    assert 'id="generationFilename"' in content
    assert "copyGenerationPrompt" in content
    assert "copyGenerationRawOutput" in content
    assert "applyGeneratedLatex" in content
    assert "createFileWithContent" in content
    assert "'/generation/validate'" in content
    assert "generation/providers/status" in content
    assert "'/generation/generate'" in content


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
    from fastapi import HTTPException
    from app.routers.export import resolve_export_download_path

    with pytest.raises(HTTPException) as exc_info:
        resolve_export_download_path("../evil.zip")

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Invalid export filename"


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
    assert "Решить неравенство 2^x > 8." in data["prompt"]
    assert "```latex```" in data["prompt"]


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
    assert second_response.json()["detail"] == "AI rate limit exceeded. Try again later."
    generation_router.rate_limit_buckets.clear()


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


def test_generation_generate_uses_provider_and_extracts_latex(monkeypatch):
    from app.routers import generation as generation_router

    async def fake_generate(prompt, provider, model):
        assert "Показательные уравнения" in prompt
        assert "Михаил Романов" in prompt
        assert provider == "ollama"
        assert model == "qwen2.5:14b"
        return (
            "```latex\n"
            r"\documentclass{article}\begin{document}Generated\end{document}"
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
    assert data["latex_code"] == r"\documentclass{article}\begin{document}Generated\end{document}"
    assert data["raw_output"].startswith("```latex")
    assert data["validation"]["valid"] is True
    assert data["validation"]["warnings"]


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
