"""Optional browser smoke tests for frontend workflows.

These tests are skipped when Playwright or browser binaries are not installed.
They exercise browser-visible regressions that static JS contract checks cannot
catch, such as duplicate submit guards and lesson review controls.
"""

from functools import partial
from http.server import SimpleHTTPRequestHandler
import json
from pathlib import Path
import socketserver
import threading
import time
from urllib.parse import urlparse

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = REPO_ROOT / "frontend"


class QuietStaticHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A002 - inherited stdlib parameter name
        return


@pytest.fixture()
def frontend_server():
    handler = partial(QuietStaticHandler, directory=str(FRONTEND_DIR))
    with socketserver.TCPServer(("127.0.0.1", 0), handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        yield f"http://127.0.0.1:{server.server_address[1]}/main.html"
        server.shutdown()
        thread.join(timeout=5)


@pytest.fixture()
def browser_page():
    playwright_api = pytest.importorskip("playwright.sync_api", reason="Playwright is not installed")

    with playwright_api.sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch()
        except Exception as exc:  # pragma: no cover - depends on local browser install
            pytest.skip(f"Playwright browser is not available: {exc}")

        page = browser.new_page()
        page_errors: list[str] = []
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))
        yield page, page_errors
        browser.close()


def fulfill_json(route, payload: dict, *, status: int = 200) -> None:
    route.fulfill(status=status, content_type="application/json", body=json.dumps(payload))


def install_frontend_backend_mocks(page, *, delay_generation_seconds: float = 0.0) -> dict[str, int]:
    calls = {"generation_jobs": 0}

    def handle(route):
        request = route.request
        parsed = urlparse(request.url)
        path = parsed.path
        method = request.method.upper()

        if path == "/api/health":
            return fulfill_json(route, {"status": "healthy"})
        if path == "/api/projects/" and method == "POST":
            return fulfill_json(route, {"id": "project-1", "name": "Smoke", "owner_id": "local-user"}, status=201)
        if path == "/api/projects/project-1" and method == "GET":
            return fulfill_json(route, {"id": "project-1", "name": "Smoke", "owner_id": "local-user"})
        if path == "/api/files/project/project-1":
            return fulfill_json(route, [{"id": "file-1", "project_id": "project-1", "name": "main.tex", "content": "\\\\documentclass{article}\\n\\\\begin{document}Smoke\\\\end{document}", "is_main": True}])
        if path == "/api/templates/":
            return fulfill_json(route, [])
        if path == "/api/files/file-1" and method == "PUT":
            return fulfill_json(route, {"id": "file-1", "project_id": "project-1", "name": "main.tex", "content": "saved", "is_main": True})
        if path == "/api/generation/presets":
            return fulfill_json(route, [{"name": "smoke", "defaults": {}}])
        if path == "/api/generation/jobs" and method == "POST":
            calls["generation_jobs"] += 1
            if delay_generation_seconds:
                time.sleep(delay_generation_seconds)
            return fulfill_json(
                route,
                {
                    "id": "job-1",
                    "status": "completed",
                    "stage": "completed",
                    "result": {
                        "latex_code": "\\\\documentclass{article}\\n\\\\begin{document}Generated smoke\\\\end{document}",
                        "raw_output": "generated",
                        "provider": "fake",
                        "model": "smoke",
                        "validation": {"valid": True, "errors": [], "warnings": []},
                        "compile_check": {"attempted": False, "success": None},
                    },
                    "error_message": None,
                },
                status=201,
            )
        if path == "/api/generation/jobs/job-1" and method == "GET":
            return fulfill_json(route, {"id": "job-1", "status": "completed", "stage": "completed", "result": {}, "error_message": None})
        if path == "/api/compile/" and method == "POST":
            return fulfill_json(route, {"status": "success", "output": "OK", "compile_time": "0.01s", "pdf_url": None})
        if path == "/api/pupils/":
            return fulfill_json(route, [{"id": "pupil-1", "display_name": "Smoke Pupil", "teacher_id": "local-teacher", "created_at": "2026-06-15T00:00:00", "updated_at": "2026-06-15T00:00:00"}])
        if path == "/api/lessons/":
            return fulfill_json(route, [{"id": "lesson-1", "pupil_id": "pupil-1", "teacher_id": "local-teacher", "topic": "Smoke lesson", "lesson_date": "2026-06-15T10:00:00", "status": "transcript_ready", "created_at": "2026-06-15T00:00:00", "updated_at": "2026-06-15T00:00:00"}])
        if path == "/api/lessons/lesson-1/transcripts":
            return fulfill_json(route, [{"id": "transcript-1", "lesson_id": "lesson-1", "recording_id": "recording-1", "provider": "fake", "language": "ru", "text": "raw smoke transcript", "edited_text": "reviewed smoke transcript", "review_status": "needs_review", "reviewed_at": None, "status": "completed", "error_message": None, "created_at": "2026-06-15T00:00:00", "updated_at": "2026-06-15T00:00:00"}])
        if path == "/api/lessons/lesson-1/documents":
            return fulfill_json(route, [{"id": "doc-1", "lesson_id": "lesson-1", "transcript_id": "transcript-1", "document_type": "check_list", "title": "Smoke checklist", "filename": "check.tex", "content_type": "application/x-tex", "provider": "fake", "prompt_template_hash": "a" * 64, "source_text_hash": "b" * 64, "source_text_kind": "edited", "status": "draft", "error_message": None, "created_at": "2026-06-15T00:00:00", "updated_at": "2026-06-15T00:00:00", "download_url": "/api/lessons/lesson-1/documents/doc-1/download"}])
        return route.fulfill(status=404, body=f"Unhandled mock route: {method} {path}")

    page.route("**/api/**", handle)
    return calls


def test_frontend_local_editor_preview_smoke(frontend_server, browser_page):
    page, page_errors = browser_page

    page.goto(frontend_server, wait_until="domcontentloaded")
    page.wait_for_selector(".CodeMirror", timeout=15_000)
    page.wait_for_selector("#fileTree", timeout=15_000)

    assert "main.tex" in page.locator("#fileTree").inner_text()

    page.evaluate(
        """
        () => {
            window.backendAvailable = false;
            window.editor.setValue('\\\\documentclass{article}\n\\\\begin{document}Offline smoke $x^2$\\\\end{document}');
        }
        """
    )
    page.click("#compileBtn")
    page.wait_for_function(
        "() => document.getElementById('statusText').textContent.includes('Локальный preview')",
        timeout=10_000,
    )

    assert "Offline smoke" in page.locator("#previewContent").inner_text()
    assert page_errors == []


def test_frontend_generation_duplicate_submit_guard_smoke(frontend_server, browser_page):
    page, page_errors = browser_page
    calls = install_frontend_backend_mocks(page, delay_generation_seconds=0.5)

    page.goto(frontend_server, wait_until="domcontentloaded")
    page.wait_for_selector(".CodeMirror", timeout=15_000)
    page.click("#generationBtn")
    page.fill("#generationTopic", "Smoke generation")
    page.fill("#generationMaterials", "x^2 + 1 = 0")
    page.select_option("#generationInsertMode", "append")

    # The second click happens while the first mocked job request is still open;
    # this catches browser-level regressions that static code checks cannot see.
    page.click("#generateLatexBtn")
    page.click("#generateLatexBtn", force=True)
    page.wait_for_function("() => !document.getElementById('generateLatexBtn').disabled", timeout=10_000)

    assert calls["generation_jobs"] == 1
    assert page_errors == []


def test_frontend_lesson_review_and_document_controls_smoke(frontend_server, browser_page):
    page, page_errors = browser_page
    install_frontend_backend_mocks(page)

    page.goto(frontend_server, wait_until="domcontentloaded")
    page.wait_for_selector(".CodeMirror", timeout=15_000)
    page.click("text=Уроки")
    page.wait_for_selector("#lessonTranscriptEditor", timeout=10_000)

    assert "reviewed smoke transcript" in page.locator("#lessonTranscriptEditor").input_value()
    assert "Smoke checklist" in page.locator("#lessonDocumentsList").inner_text()
    assert "draft · edited" in page.locator("#lessonDocumentsList").inner_text()
    assert page.locator("button", has_text="Сохранить review").count() == 1
    assert page.locator("button", has_text="Документы").count() == 1
    assert page_errors == []
