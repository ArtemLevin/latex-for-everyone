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
    local_script_urls = re.findall(r'<script\s+src="(js/[^"]+)"', main_html)
    local_scripts = [script_url.split("?", 1)[0] for script_url in local_script_urls]

    assert local_scripts == EXPECTED_LOCAL_SCRIPT_ORDER
    assert "js/main.js" not in local_scripts
    assert all("?v=" in script_url for script_url in local_script_urls)


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
    assert "LESSON_RECORDING_MIME_CANDIDATES" in lessons_js
    assert "lessonRecordingConsent" in lessons_js
    assert "formatLessonRecordingDuration" in lessons_js
    assert "data-recording-state" in lessons_js
    assert "lesson-audio-preview" in lessons_js
    assert "loadLessonTranscripts" in lessons_js
    assert "saveLessonTranscriptReview" in lessons_js
    assert "lessonTranscriptEditor" in lessons_js
    assert "review_status" in lessons_js


def test_frontend_renders_user_controlled_file_names_and_toasts_as_text():
    files_js = (FRONTEND_DIR / "js" / "04-files.js").read_text(encoding="utf-8")
    settings_js = (FRONTEND_DIR / "js" / "09-ui-settings.js").read_text(encoding="utf-8")

    assert '<span class="file-name">${file.name}</span>' not in files_js
    assert "name.textContent = file.name" in files_js
    assert "renameButton.addEventListener('click'" in files_js
    assert "deleteButton.addEventListener('click'" in files_js
    assert "toast.innerHTML = `${icons[type] || icons.info}<span>${message}</span>`" not in settings_js
    assert "text.textContent = message" in settings_js


def test_generation_frontend_does_not_auto_retry_after_request_completion():
    generation_js = (FRONTEND_DIR / "js" / "07-generation.js").read_text(encoding="utf-8")
    api_js = (FRONTEND_DIR / "js" / "02-api.js").read_text(encoding="utf-8")

    assert generation_js.count("async function runGenerationRequest") == 1
    assert generation_js.count("async function generateLatexFromAi") == 1
    assert generation_js.count("async function retryLastGeneration") == 1
    assert generation_js.count("async function regenerateWithLatexMode") == 1
    assert generation_js.count("await runGenerationRequest(cloneGenerationRequest(lastGenerationRequest), 'retryGenerationBtn');") == 1
    assert "finally {" in generation_js
    state_js = (FRONTEND_DIR / "js" / "01-state.js").read_text(encoding="utf-8")

    assert "let generationRequestInFlight = false" in state_js
    assert "let generationRateLimitedUntil = 0" in state_js
    assert "if (generationRequestInFlight)" in generation_js
    assert "generationRequestInFlight = true" in generation_js
    assert "generationRequestInFlight = false" in generation_js
    assert "generationRateLimitedUntil = retryAfter > 0" in generation_js
    assert "const waitMs = generationRateLimitedUntil - Date.now()" in generation_js
    assert "const GENERATION_ACTION_BUTTON_IDS" in generation_js
    assert "setGenerationActionButtonsDisabled(true, loadingButtonId)" in generation_js
    assert "setGenerationActionButtonsDisabled(false, loadingButtonId)" in generation_js
    main_html = (FRONTEND_DIR / "main.html").read_text(encoding="utf-8")
    assert 'type="button" class="compile-btn" onclick="generateLatexFromAi()" id="generateLatexBtn"' in main_html
    assert "error.status = response.status" in api_js
    assert "error.retryAfter = response.headers.get('Retry-After')" in api_js
