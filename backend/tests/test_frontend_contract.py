"""Static frontend contract checks that do not require a browser."""

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = REPO_ROOT / "frontend"
EXPECTED_LOCAL_SCRIPT_ORDER = [
    "js/01-state.js",
    "js/02-api.js",
    "js/03-init.js",
    "js/04-files.js",
    "js/05-compile-preview.js",
    "js/06-toolbar-view.js",
    "js/07-generation.js",
    "js/08-templates-export.js",
    "js/09-ui-settings.js",
    "js/10-lessons.js",
]


def test_frontend_main_html_uses_expected_numbered_script_order():
    main_html = (FRONTEND_DIR / "main.html").read_text(encoding="utf-8")
    local_scripts = re.findall(r'<script\s+src="(js/[^"]+)"', main_html)

    assert local_scripts == EXPECTED_LOCAL_SCRIPT_ORDER
    assert "js/main.js" not in local_scripts


def test_legacy_frontend_main_bundle_is_not_present():
    assert not (FRONTEND_DIR / "js" / "main.js").exists()


def test_lesson_frontend_entrypoint_and_dom_contract_are_present():
    main_html = (FRONTEND_DIR / "main.html").read_text(encoding="utf-8")
    lessons_js = (FRONTEND_DIR / "js" / "10-lessons.js").read_text(encoding="utf-8")

    assert "switchSidebarTab('lessons'" in main_html
    assert "js/10-lessons.js" in main_html
    assert "function renderLessonSidebar" in lessons_js
    assert "startLessonProcessingJob" in lessons_js
    assert "MediaRecorder" in lessons_js
