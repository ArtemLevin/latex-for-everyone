# Latexed Reference Files

Use these files as the first references for future work. The examples are intentionally Latexed-specific.

## Project entry points

### FastAPI app

Reference: `backend/app/main.py`

Use it for:

- app metadata and docs URLs;
- middleware registration;
- CORS/trusted host behavior;
- router prefixes;
- health/root endpoint shape.

### Frontend shell

Reference: `frontend/main.html`

Use it for:

- DOM IDs and modal structure;
- third-party libraries loaded from CDNs;
- local CSS and JS load order;
- visible UI text and controls.

Script order matters and is covered by frontend contract tests:

```text
01-state.js → 02-api.js → 03-init.js → 04-files.js →
05-compile-preview.js → 06-toolbar-view.js → 07-generation.js →
08-templates-export.js → 09-ui-settings.js
```

The old monolithic `frontend/js/main.js` bundle has been removed; do not reintroduce it as a parallel entrypoint.

## Backend references

### Schemas

Reference: `backend/app/schemas.py`

Canonical contracts include:

- `ProjectCreate`, `ProjectUpdate`, `ProjectResponse`, `ProjectDetailResponse`;
- `FileCreate`, `FileUpdate`, `FileResponse`;
- `CompileRequest`, `RawCompileRequest`, `LatexCompileResult`, `CompileResponse`, `CompileHistoryResponse`;
- `PDFGenerationResult`, `ExportRequest`, `ExportResponse`;
- generation request/response/validation/provider/preset schemas;
- snapshot and generic response schemas.

Before adding a schema:

1. Search for an existing model with `rg -n "class .*Response|class .*Request|class .*Create|class .*Update" backend/app/schemas.py`.
2. Prefer extending or reusing an existing contract.
3. Document public API changes.

### Models and database

References:

- `backend/app/models.py`
- `backend/app/database.py`
- `backend/app/time_utils.py`
- `backend/alembic/`

Persisted entities:

- `Project`
- `File`
- `CompileHistory`
- `ProjectSnapshot`
- `GenerationHistory`
- `Pupil`
- `Lesson`
- `LessonAudioRecording`
- `LessonTranscript`
- `LessonGeneratedDocument`
- `LessonProcessingJob`

Guidelines:

- Keep models persistence-focused.
- Use `utc_now()` from `backend/app/time_utils.py` for new timestamp defaults and manual `updated_at` changes; do not call `datetime.utcnow()` directly in app code.
- Use migrations for schema changes when practical.
- Do not commit local SQLite databases.

### Pupils and lessons routers

References:

- `backend/app/routers/pupils.py`
- `backend/app/routers/lessons.py`
- `backend/app/services/lesson_service.py`
- `backend/app/services/audio_storage.py`
- `backend/app/services/transcription.py`
- `backend/app/services/lesson_documents.py`
- `backend/app/services/lesson_jobs.py`
- `backend/app/prompts/lesson/check_list.txt`
- `backend/app/prompts/lesson/pupil_mistakes.txt`
- `frontend/js/10-lessons.js`

Use them for the lesson foundation: pupil CRUD, lesson CRUD, lesson filtering by pupil/date, the placeholder teacher ownership boundary, safe audio recording upload through `AudioStorageService` (filename/type/size checks, generated storage paths, checksum metadata, best-effort duration probing), explicit transcription through `TranscriptionService`, checklist/mistakes-review document artifacts through `LessonDocumentGenerationService`, and processing-job status orchestration through `LessonProcessingJobService`. The current teacher scope is supplied by `get_current_teacher_id()` and returns `local-teacher` until real auth is introduced. Frontend lesson concerns live in `frontend/js/10-lessons.js`; routers should remain service-bound HTTP adapters.

### Projects and files routers

References:

- `backend/app/routers/projects.py`
- `backend/app/routers/files.py`

Use them for current CRUD behavior, snapshots, duplication, upload flows, and existing `TestClient` patterns. Note that direct SQLAlchemy use in these routers is legacy/current style; do not expand it for complex new behavior if a service is more appropriate.

### Compile flow

References:

- `backend/app/routers/compile.py`
- `backend/app/services/latex_compiler.py`
- `backend/app/services/latex_sanitizer.py`

Good patterns:

- typed service result with `LatexCompileResult`;
- file map sanitization before writing to temporary work directories;
- `Path(filename).name` for compile entrypoint safety;
- bounded compile timeout and output/error fields;
- generated PDF stored under configured compile output directory.

### Export flow

References:

- `backend/app/routers/export.py`
- `backend/app/services/pdf_generator.py`

Use them for PDF/HTML/TEX export response shape, generated file download behavior, and path-safety expectations.

### AI generation flow

References:

- `backend/app/routers/generation.py`
- `backend/app/services/ai_generation.py`
- `backend/app/services/prompt_builder.py`
- `backend/app/services/latex_validator.py`

Good patterns:

- enforce AI rate limits and text limits at API boundaries;
- build prompt separately from provider calls;
- sanitize provider errors unless explicitly configured otherwise;
- extract LaTeX code before validation/insertion;
- validate generated LaTeX structure;
- log metadata, hashes, counts, and status instead of full user content.

### Lesson/transcription preparation artifacts

References:

- `PLAN.md` section 10
- `transcibe.py`
- `backend/app/prompts/lesson/check_list.txt`
- `backend/app/prompts/lesson/pupil_mistakes.txt`
- `frontend/js/10-lessons.js`

Current status:

- The lesson workflow currently includes backend-only `Pupil`/`Lesson` CRUD, safe audio upload metadata/storage with checksums and optional duration metadata, `LessonTranscript` persistence, `LessonGeneratedDocument` metadata/artifacts, and `LessonProcessingJob` polling/status records through typed service adapters.
- `transcibe.py` is a legacy-named standalone CLI script, not a backend service. It is contained behind the optional legacy adapter and must not be imported from routers.
- `backend/app/prompts/lesson/check_list.txt` and `backend/app/prompts/lesson/pupil_mistakes.txt` are parameterized prompt templates loaded through `LessonPromptService`.
- Prompt-loader tests guard against the removed hardcoded student-like `Николь` example returning to production templates.

Required boundaries for future work:

1. `Pupil`/`Lesson` CRUD, lesson-audio upload/storage, and transcription are backend-only foundations; transcription must stay behind `TranscriptionService` and must not call AI document-generation providers.
2. Transcription must go through the typed service adapter with a fake provider for tests; routers must not import the legacy `transcibe.py` script.
3. Lesson document generation must prefer structured provider output that the backend validates before building escaped LaTeX.
4. Downloads must resolve by persisted lesson/document metadata and trusted roots, not by arbitrary user-provided filenames.

### Tests

Reference: `backend/tests/test_api.py`

Current style:

- `TestClient(app)`;
- dependency override for `get_db`;
- test SQLite database;
- `setup_db` fixture that creates/drops metadata;
- direct API assertions for health, projects, files, pupils, lessons, templates, and selected LaTeX service helpers.

Add tests here or split into additional files under `backend/tests/` when a feature grows large.

## Frontend references

### State and API bootstrap

References:

- `frontend/js/01-state.js`
- `frontend/js/02-api.js`
- `frontend/js/03-init.js`

Use them for:

- API base URL resolution;
- backend availability state;
- startup flow;
- project/file bootstrap;
- editor initialization and keyboard shortcuts.

### File tree

Reference: `frontend/js/04-files.js`

Use it for file selection, creation, renaming, deletion, duplication, upload, and context menu behavior.

### Compile and preview

Reference: `frontend/js/05-compile-preview.js`

Use it for server compile calls, local preview fallback, PDF preview embedding, error panel updates, and compile status behavior.

### Toolbar, templates, export, AI, settings

References:

- `frontend/js/06-toolbar-view.js`
- `frontend/js/07-generation.js`
- `frontend/js/08-templates-export.js`
- `frontend/js/09-ui-settings.js`

Use the existing helper/UI patterns instead of creating parallel modal/status/toast systems.

## Good examples to follow

### Typed service result

```python
class PDFGenerationResult(BaseModel):
    success: bool
    filename: str | None = None
    size: int | None = None
    error: str | None = None
```

Why:

- routers get a stable contract;
- implementation details stay in the service;
- error/success fields are explicit.

### Safe frontend backend fallback

```javascript
try {
    await apiRequest('/health');
    setBackendAvailability(true);
} catch (error) {
    setBackendAvailability(false);
    compileLatexLocal();
}
```

Why:

- the editor remains useful without a backend;
- user feedback remains explicit;
- API availability is centralized.

### Safe LaTeX validation helper

```python
validation = validate_latex_document(latex_code)
return GenerationValidationResponse(**validation)
```

Why:

- LaTeX structure checks are reusable;
- API response shape is typed;
- generated content is checked before insertion/compilation.

## Anti-references

Do not follow or add examples involving:

- booking, calendar slots, customer email, meeting settings, or colleagues;
- `/app/api`, `/app/db/repositories`, or `/tests/services` paths unless those paths are actually created in this repository;
- `make lint` or `make typecheck` unless the Makefile is updated to provide them;
- model methods that perform HTTP, subprocess, file-system, or AI-provider side effects;
- frontend code that bypasses `apiRequest` for normal backend API calls;
- logging full prompts, full generated LaTeX, uploaded source material, or generated PDFs.

## Reference update policy

Update this file when:

- a new backend service/module becomes the canonical pattern;
- frontend script ownership changes;
- API schemas are reorganized;
- checks or Makefile targets change;
- docs discover and remove stale non-Latexed examples.
