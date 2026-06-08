"""Optional browser smoke test for the frontend local/offline workflow.

This test is skipped when Playwright or browser binaries are not installed. It is
intended for the optional `make frontend-e2e` target, not as a replacement for the
static frontend contract tests.
"""

from functools import partial
from http.server import SimpleHTTPRequestHandler
from pathlib import Path
import socketserver
import threading

import pytest

try:
    from playwright.sync_api import sync_playwright
except Exception:  # pragma: no cover - depends on optional local dependency
    sync_playwright = None


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


def test_frontend_local_editor_preview_smoke(frontend_server):
    if sync_playwright is None:
        pytest.skip("Playwright is not installed")

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch()
        except Exception as exc:  # pragma: no cover - depends on local browser install
            pytest.skip(f"Playwright browser is not available: {exc}")

        page = browser.new_page()
        page_errors: list[str] = []
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))

        page.goto(frontend_server, wait_until="domcontentloaded")
        page.wait_for_selector(".CodeMirror", timeout=15_000)
        page.wait_for_selector("#fileTree", timeout=15_000)

        assert "main.tex" in page.locator("#fileTree").inner_text()

        page.evaluate(
            """
            () => {
                window.backendAvailable = false;
                window.editor.setValue('\\\\documentclass{article}\\n\\\\begin{document}Offline smoke $x^2$\\\\end{document}');
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
        browser.close()
