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

    assert {"projects", "files", "compile_history", "project_snapshots", "alembic_version"}.issubset(tables)
    assert "owner_id" in {column["name"] for column in inspector.get_columns("projects")}
    assert "ix_projects_owner_id" in {index["name"] for index in inspector.get_indexes("projects")}


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
    old_pdf.write_bytes(b"old")
    new_pdf.write_bytes(b"new")
    old_txt.write_text("old")

    old_time = time.time() - 3600
    os.utime(old_pdf, (old_time, old_time))
    os.utime(old_txt, (old_time, old_time))

    removed = cleanup_old_files(tmp_path, max_age_seconds=60, suffixes={".pdf"})

    assert removed == 1
    assert not old_pdf.exists()
    assert new_pdf.exists()
    assert old_txt.exists()


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
    assert 'src="js/01-state.js"' in content
    assert 'src="js/09-ui-settings.js"' in content
    assert 'id="generationModal"' in content
    assert 'id="generationTopic"' in content
    assert 'id="generationMaterials"' in content
    assert 'id="generationLanguage"' in content
    assert 'id="generationContentSourceMode"' in content
    assert 'value="gemma4"' in content
    assert "collectGenerationRequest" in content
    assert "generateLatexFromAi" in content
    assert "main_file_name" in content
    assert "validateCurrentLatex" in content
    assert "checkGenerationProvider" in content
    assert 'id="generationInsertMode"' in content
    assert "language: getGenerationFieldValue('generationLanguage')" in content
    assert "content_source_mode: getGenerationFieldValue('generationContentSourceMode')" in content
    assert 'id="generationFilename"' in content
    assert "copyGenerationPrompt" in content
    assert "copyGenerationRawOutput" in content
    assert "applyGeneratedLatex" in content
    assert "createFileWithContent" in content
    assert "'/generation/validate'" in content
    assert "generation/providers/status" in content
    assert "'/generation/generate'" in content
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
    assert presets[0]["defaults"]["language"] == "русский"
    assert presets[0]["defaults"]["content_source_mode"] == "materials_only"


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
    assert "ЯЗЫК ДОКУМЕНТА" in data["prompt"]
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


def test_ai_generation_service_defaults_to_gemma4_for_ollama(monkeypatch):
    from app.config import settings
    from app.services.ai_generation import AIGenerationService

    monkeypatch.setattr(settings, "AI_PROVIDER", "ollama")
    monkeypatch.setattr(settings, "OLLAMA_MODEL", "gemma4")

    provider, model = AIGenerationService().resolve_provider_model()

    assert provider == "ollama"
    assert model == "gemma4"


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


def test_generation_generate_strips_accidental_model_preamble(monkeypatch):
    from app.routers import generation as generation_router

    async def fake_generate(prompt, provider, model):
        return (
            "```latex\n"
            r"\documentclass{article}\usepackage{graphicx}\begin{document}Generated full doc\end{document}"
            "\n```",
            "ollama",
            "gemma4",
        )

    monkeypatch.setattr(generation_router.ai_generator, "generate", fake_generate)

    response = client.post(
        "/api/generation/generate",
        json={"fields": {"topic": "Преамбула"}, "materials": "Сделать пособие."},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["latex_code"].count(r"\documentclass") == 1
    assert r"\usepackage{graphicx}" not in data["latex_code"]
    assert "Generated full doc" in data["latex_code"]
    assert data["validation"]["valid"] is True




def test_generation_generate_repairs_latex_when_compile_check_fails(monkeypatch):
    from app.routers import generation as generation_router
    from app.config import settings
    from app.schemas import LatexCompileResult

    prompts = []
    compile_inputs = []

    async def fake_generate(prompt, provider, model):
        prompts.append(prompt)
        if len(prompts) == 1:
            return (
                "```latex\n"
                r"\section{Broken}\begin{infoblock}{Важно}Нет закрытия"
                "\n```",
                "ollama",
                "gemma4",
            )
        return (
            "```latex\n"
            r"\section{Fixed}\begin{infoblock}{Важно}Закрыто\end{infoblock}"
            "\n```",
            "ollama",
            "gemma4",
        )

    def fake_compile(main_content, files, main_filename="main.tex"):
        compile_inputs.append(main_content)
        if len(compile_inputs) == 1:
            return LatexCompileResult(status="error", error=r"! LaTeX Error: \begin{infoblock} ended by \end{document}.")
        return LatexCompileResult(status="success", output="OK", compile_time="0.01s", pdf_url="/api/compile/download/test.pdf")

    monkeypatch.setattr(settings, "AI_COMPILE_CHECK_ENABLED", True)
    monkeypatch.setattr(settings, "AI_REPAIR_ATTEMPTS", 1)
    monkeypatch.setattr(generation_router.shutil, "which", lambda compiler: "/usr/bin/pdflatex")
    monkeypatch.setattr(generation_router.ai_generator, "generate", fake_generate)
    monkeypatch.setattr(generation_router.generation_compiler, "compile", fake_compile)

    response = client.post(
        "/api/generation/generate",
        json={"fields": {"topic": "Компилируемость"}, "materials": "Сделать пособие."},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(prompts) == 2
    assert "исправляешь LaTeX BODY" in prompts[1]
    assert "ended by" in prompts[1]
    assert len(compile_inputs) == 2
    assert "Broken" in compile_inputs[0]
    assert "Fixed" in compile_inputs[1]
    assert "Закрыто" in data["latex_code"]
    assert data["raw_output"].startswith("```latex")
    assert data["compile_check"] == {
        "attempted": True,
        "success": True,
        "attempts": 2,
        "repaired": True,
        "skipped_reason": None,
        "error": None,
    }


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
