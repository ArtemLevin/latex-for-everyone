# Latexed

**Latexed** is an online LaTeX editor with a FastAPI backend, a single-page HTML frontend, live/local preview, server-side compilation, and export endpoints.

## Stack

- **FastAPI** — backend API
- **SQLAlchemy** — ORM
- **SQLite/PostgreSQL** — database
- **pdflatex** — LaTeX compiler binary used by compile/export flows
- **CodeMirror + KaTeX** — frontend editor and local preview
- **Docker + Nginx** — containerized deployment path
- **Celery + Redis** — async task queue scaffolding for production tasks

## Repository layout

```text
backend/            FastAPI application, tests, Docker/Nginx config
frontend/main.html  Browser editor UI markup
frontend/css/       Frontend styles
frontend/js/        Frontend state, API, editor, compile/export, AI UI scripts
```

Architecture overview with UML/Mermaid diagrams is available in [`docs/uml-diagrams.md`](docs/uml-diagrams.md). The current service-state analysis and development roadmap are maintained in [`PLAN.md`](PLAN.md). Production and local troubleshooting guidance is maintained in [`docs/operations.md`](docs/operations.md).

## Quick start

### 1. Install Python dependencies with uv

This repository includes `pyproject.toml` for `uv`. From the repository root:

```bash
uv sync --all-groups
```

If you prefer the legacy requirements file, use:

```bash
uv pip install -r backend/requirements.txt
```

### 2. Start the backend

Using Make:

```bash
make backend
```

Or directly with `uv`:

```bash
cd backend
uv run --project .. uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Useful backend URLs:

- API docs: http://localhost:8000/api/docs
- Health check: http://localhost:8000/api/health
- Readiness check: http://localhost:8000/api/ready

> Server-side compilation and PDF export require `pdflatex` to be installed and available on `PATH` unless you override `LATEX_COMPILER`. Use `make latex-check` or `GET /api/ready` to verify compiler and Russian/T2A package readiness.

### 3. Start the frontend

Using Make:

```bash
make frontend
```

Or directly from the repository root with any static server:

```bash
python3 -m http.server 8080 --directory frontend
```

If your system uses the `python` executable instead of `python3`, override the Makefile variable when needed:

```bash
make frontend PYTHON=python
```

Open http://localhost:8080/main.html.

The frontend will try to connect to `http://localhost:8000/api` when it is served from a local development port such as `8080`. If the backend is not reachable, the editor remains usable in local preview/export fallback mode.

The active frontend entrypoint is the ordered script set declared in `frontend/main.html` (`01-state.js` through `09-ui-settings.js`). The old monolithic `frontend/js/main.js` legacy bundle has been removed; script ordering is protected by backend contract tests.

### 4. Docker backend

```bash
cd backend
docker-compose up --build
```

The Docker image installs a TeX Live distribution, so backend compilation/export is available inside the container.

## Makefile commands

The root `Makefile` wraps the common `uv`, test, server, Docker, and cleanup workflows.

| Command | Description |
|---------|-------------|
| `make help` | Show all available targets. |
| `make sync` | Run `uv sync --all-groups` to install app and dev dependencies. |
| `make lock` | Refresh `uv.lock` from `pyproject.toml`. |
| `make backend` | Run the FastAPI backend on `BACKEND_PORT` (default `8000`). |
| `make frontend` | Serve `frontend/main.html` on `FRONTEND_PORT` (default `8080`). |
| `make open` | Print backend, docs, health, and frontend URLs. |
| `make health` | Call `GET /api/health`. |
| `make ai-provider-status` | Check configured AI provider/model availability. |
| `make ai-validate-smoke` | Validate a minimal LaTeX document through the generation validator. |
| `make test` | Run backend tests with `uv`. |
| `make frontend-check` | Run `node --check` for `frontend/js/*.js`. |
| `make frontend-e2e` | Run optional Playwright browser smoke tests for local preview, generation duplicate-submit guard, and lesson review/document controls. Skips when Playwright/browser binaries are unavailable. |
| `make generation-worker` | Run the external AI generation worker loop for queued jobs. |
| `make generation-worker-once` | Claim and run at most one queued AI generation job, useful for smoke tests and one-shot workers. |
| `make generation-worker-recover-stale` | Requeue stale running AI generation jobs when stale recovery is configured. |
| `make check` | Run Python compile check, frontend syntax check, and backend tests. |
| `make migrate` | Run Alembic migrations. |
| `make migration MSG="..."` | Create an Alembic autogeneration revision. |
| `make clean-artifacts-dry-run` | Report stale trusted runtime artifacts that cleanup would remove. |
| `make clean-artifacts` | Safely remove stale trusted runtime artifacts using `ARTIFACT_TTL_SECONDS`. |
| `make docker-up` | Build and start Docker Compose services. |
| `make docker-down` | Stop Docker Compose services. |
| `make clean` | Remove local DB files and Python/test caches. |
| `make clean-venv` | Remove the root `.venv`. |

Useful overrides:

```bash
make backend BACKEND_PORT=9000
make frontend FRONTEND_PORT=3000
make frontend PYTHON=python
make migration MSG="add users table"
make ai-provider-status AI_PROVIDER=ollama AI_MODEL=qwen2.5:3b
```

## uv notes

- `pyproject.toml` is the source for `uv sync` and includes runtime dependencies plus a `dev` dependency group for tests.
- The project is configured with `package = false`, so `uv` manages the environment without requiring this repository to be installed as a Python package.
- Backend commands run from `backend/` so `app.main:app` imports resolve the same way they do with plain `uvicorn`.
- `requirements.txt` remains available for Docker and pip-based workflows.


## Health vs readiness

Latexed exposes two operational status endpoints:

- `GET /api/health` is a lightweight liveness check. It means the backend process is running and can answer HTTP requests.
- `GET /api/ready` is a readiness check. It reports structured statuses for `database`, `compiler`, `latex_packages`, `artifact_dirs`, and optional `transcription`, and returns an overall `ready`, `degraded`, or `not_ready` status.
- `GET /api/transcription/status` reports only the configured transcription runtime: selected/effective provider, optional Python package discovery, `ffmpeg`/`ffprobe` availability, model settings, and install hints.

When `pdflatex` or required Russian/T2A LaTeX packages are missing, readiness is reported as `degraded`: project/file CRUD, templates, prompt preview, validation, and frontend local preview can still be useful, but backend server-side compile/export PDF flows are not ready. When an enabled transcription provider is missing optional packages or media tools, readiness is also `degraded`; the editor and compile flows can continue, but lesson transcription must be fixed before use. Run `make latex-check` in the target environment to verify the TeX Live runtime.

## Frontend browser smoke tests

`make frontend-e2e` runs optional Playwright smoke tests against the static frontend served from `frontend/main.html`. The suite currently checks local/offline preview, browser-level duplicate AI generation submit protection with mocked `/api/generation/jobs`, and lesson transcript review/document controls with mocked lesson APIs. These tests are intentionally optional: if Playwright or browser binaries are not installed, pytest reports skips rather than failing the backend suite. Use them before merging frontend UX changes that static `node --check` and contract tests cannot fully exercise.

## Runtime artifacts and cleanup

Latexed creates local runtime files during development and tests. These files are intentionally ignored by git:

- SQLite databases such as `latexed.db`, `test_latexed.db`, `*.sqlite`, and `*.sqlite3`;
- Python/test caches such as `__pycache__/` and `.pytest_cache/`;
- generated compile/export/upload artifacts under the configured runtime directories, for example `/tmp/latexed_compiles` and `/tmp/latexed_uploads`.

Generated artifact locations are intentionally separated by purpose:

- compile PDF downloads are served only from `${COMPILE_WORK_DIR}/pdfs`;
- export downloads are served only from `${UPLOAD_DIR}/exports`;
- uploaded user files and temporary upload state live under `${UPLOAD_DIR}`;
- lesson audio recordings live under `${LESSON_ARTIFACT_ROOT}` when set, otherwise under `${UPLOAD_DIR}/lessons`.

Download endpoints validate artifact filenames through a shared safe-path resolver: path traversal, nested paths, unsupported extensions, and files outside the configured artifact roots are rejected. Compile downloads currently allow PDF files only; export downloads allow PDF, HTML, and ZIP artifacts. Cleanup uses the same trusted-root policy and never treats the broad upload directory as a wildcard root. The configured cleanup roots are `${COMPILE_WORK_DIR}/pdfs`, `${UPLOAD_DIR}/exports`, and `${LESSON_ARTIFACT_ROOT}` or `${UPLOAD_DIR}/lessons`; lesson cleanup is recursive but suffix-allowlisted to known audio/document artifact types.

Automatic and manual cleanup use `ARTIFACT_TTL_SECONDS`; set it to `0` to disable age-based cleanup. `make clean-artifacts-dry-run` prints a JSON report with files that would be deleted, skipped counts, byte totals, errors, and duration. `make clean-artifacts` runs the same safe cleanup with `--commit`; use it only when no backend process is actively writing artifacts. Production cron/systemd timers should call `backend/scripts/clean_artifacts.py` first without `--commit`, review the report in logs, and then schedule `--commit` with an explicit retention window.

Use `make clean` to remove local SQLite databases and Python/test caches from the repository working tree. Do not commit local databases, generated PDFs, uploaded user files, `.env` files, or provider credentials.

## Timestamp policy

Backend application code uses a shared `utc_now()` helper from `backend/app/time_utils.py` for timestamp defaults and manual `updated_at` changes. Avoid direct `datetime.utcnow()` calls in new code; the test suite includes a regression check for this policy.

## Lesson/transcription preparation inventory

The lesson workflow is implemented incrementally. The backend now has pupil/lesson CRUD, safe lesson-audio upload/storage, synchronous transcription, optional `faster-whisper`/legacy transcription adapters, and deterministic lesson-document generation for backend tests; frontend workflow and production AI/provider orchestration remain future work. The current checkout also contains the legacy transcription CLI and backend-owned lesson prompt templates:

- `transcribe.py` is a standalone Whisper/ffmpeg-oriented CLI script. Keep it behind the contained legacy adapter; do not build router contracts around this script. It imports `whisper`, shells out to `ffmpeg`/`ffprobe`, defines local audio extensions and default model/language values, and is not a FastAPI service.
- `backend/app/prompts/lesson/check_list.txt` is the parameterized prompt template for a lesson checklist document. The former hardcoded student-like text has been replaced with template placeholders.
- `backend/app/prompts/lesson/pupil_mistakes.txt` is the parameterized prompt template for a personalized mistakes-review document.

Boundary policy for the remaining transcription/document-generation iterations:

- Do not import or call `transcibe.py` from routers. The backend boundary is `backend/app/services/transcription.py`, which exposes a typed provider registry/contract, a fake provider for tests, an optional `faster_whisper` provider, and the legacy CLI typo behind a contained adapter.
- Prompt templates must be loaded through `LessonPromptService`; routers must not read prompt files directly.
- The backend-owned locations are `backend/app/services/transcription.py`, `backend/app/prompts/lesson/check_list.txt`, and `backend/app/prompts/lesson/pupil_mistakes.txt`.
- Audio upload is limited to validated storage metadata under `POST /api/lessons/{lesson_id}/recordings`; transcription is started explicitly through `POST /api/lessons/{lesson_id}/transcribe`; document generation is started explicitly through `POST /api/lessons/{lesson_id}/documents/generate` and currently persists safe `.tex` artifacts only.

## Database migrations

Alembic is the source of truth for schema changes. The repository includes Alembic revisions for the current project/file/history schema, AI generation history, and the lesson foundation (`pupils`, `lessons`, `lesson_audio_recordings`, `lesson_transcripts`, `lesson_generated_documents`, `lesson_processing_jobs`). Local development still keeps `AUTO_CREATE_TABLES=true` by default so a fresh SQLite checkout starts quickly, and startup performs small compatibility patches for older local `generation_history` tables missing token-usage columns and stale lesson workflow tables missing newly added metadata columns such as `sha256_checksum`, transcript review fields, or persisted job payload fields. Production deployments should set `AUTO_CREATE_TABLES=false` and run migrations explicitly before serving traffic.

Recommended workflow:

```bash
make migrate
make migration MSG="describe schema change"
# review backend/alembic/versions/*.py
make migrate
```

When changing `backend/app/models.py`, create or update an Alembic revision in the same PR and verify it against a disposable database. If you have an old local SQLite database that was created before Alembic tracking existed, either remove it with `make clean` before `make migrate` or stamp it manually only after confirming its schema matches the baseline.

## Lesson backend foundation

The first lesson-workflow implementation slice is backend-only. It adds `Pupil` and `Lesson` persistence, Alembic migration coverage, typed Pydantic schemas, service-layer CRUD, and `/api/pupils` plus `/api/lessons` routers. Current ownership uses the MVP identity resolver described below: local development falls back to `LOCAL_USER_ID=local-teacher`, and trusted deployments can pass `X-Latexed-User` (or the header named by `TRUSTED_USER_HEADER`) from an authenticated reverse proxy. Project, file, compile/export, AI-generation, pupil, lesson, transcript, document, and processing-job queries are scoped through this identity so direct cross-user IDs return 404 instead of leaking resource existence.

This foundation now includes safe audio upload metadata/storage under `POST /api/lessons/{lesson_id}/recordings` with checksum metadata and best-effort duration probing, a synchronous transcription adapter endpoint at `POST /api/lessons/{lesson_id}/transcribe`, transcript review endpoints for list/get/update before document generation, review-aware lesson document generation/download endpoints for checklist and mistakes-review `.tex` artifacts, and processing-job endpoints for start/list/poll status. Lesson jobs can run inline for local/dev compatibility or be queued for background execution via persisted job ids. The transcription default provider is disabled, `faster_whisper` is an optional runtime install for production transcription, document generation defaults to a deterministic fake provider for backend coverage, and production external-worker orchestration remains future work; a lightweight frontend sidebar panel is available under the `Уроки` tab.

The browser UI includes a lightweight `Уроки` sidebar tab loaded by `frontend/js/10-lessons.js`. It lets a teacher create/select pupils and lessons, record audio with `MediaRecorder` when available or upload an audio file manually, start transcription/document generation or the full processing job, review/edit transcript text before generation, and open generated document download links. The recording panel now chooses a supported audio MIME type, requires an explicit consent checkbox before microphone capture, shows recording state/timer/size metrics, and renders an audio preview before upload. When the backend is offline, the tab shows a degraded state instead of breaking the editor.

## Auth and ownership MVP

Latexed currently uses a trusted-header MVP instead of a full login/session system. In local single-user mode, requests without an identity header use `LOCAL_USER_ID=local-teacher`, preserving the existing development workflow. In a multi-user deployment, terminate real authentication at a trusted reverse proxy and pass the normalized user id to the backend in `X-Latexed-User` or in the header configured by `TRUSTED_USER_HEADER`. Do not expose this header directly to untrusted clients without a proxy that strips spoofed incoming values.

The backend rejects blank or control-character identities, persists new projects with the resolved `owner_id`, and uses the same identity as the lesson `teacher_id`. Direct-ID access to another user's projects, files, compile history, generation history/jobs, exports, pupils, lessons, transcripts, documents, and processing jobs is intentionally reported as `404` to avoid revealing whether the resource exists.

## Frontend/backend integration

`frontend/main.html` loads `frontend/css/app.css` and ordered scripts from `frontend/js/`; the frontend startup flow:

1. calls `GET /api/health`;
2. loads a saved project from `localStorage` or creates a new one with the `article` template;
3. loads project files from `GET /api/files/project/{project_id}`;
4. loads templates from `GET /api/templates/`;
5. autosaves the current file with `PUT /api/files/{file_id}`;
6. waits for an explicit user action before compiling; the **Компиляция** button or `Ctrl+Enter` calls `POST /api/compile/` and embeds returned PDFs with `/api/compile/download/{filename}`;
7. exports through `/api/export/pdf`, `/api/export/html`, and `/api/export/tex` when the backend is online;
8. opens the AI generation dialog with a playful rotating wait state, can check the selected AI provider/model, sends prompt fields to `/api/generation/generate` (default `latex_mode=safe` for maximum compile success), receives backend-wrapped `latex_code` plus a best-effort `compile_check` result and estimated input/output token usage for the valid generation, pauses on failed validation/compile-check with repair/retry actions, and only inserts the document automatically after checks pass. Right-clicking a generated file can open **Исследование AI-документа** with the prompt/preview, AI run count, token totals, provider/model, validation and compile-check metadata.

### Configuring the API base URL

The frontend resolves its API base URL in this order:

1. `window.LATEXED_API_BASE_URL`, for example:

   ```html
   <script>
     window.LATEXED_API_BASE_URL = 'https://example.com/api';
   </script>
   ```

2. a page-level meta tag:

   ```html
   <meta name="latexed-api-base-url" content="https://example.com/api">
   ```

3. same-origin `/api` when served by the backend or reverse proxy;
4. `http://localhost:8000/api` when served locally from another localhost port or from `file://`.

### CORS notes

For separate local frontend/backend processes, ensure `CORS_ORIGINS` includes the frontend origin. The default configuration includes:

```text
http://localhost:3000
http://localhost:8080
```

If you serve the frontend from a different port or host, update `CORS_ORIGINS` accordingly.

### Reverse proxy notes

For production, the simplest shape is:

- serve `frontend/main.html` and frontend assets from the public origin;
- proxy `/api/*` to the FastAPI backend;
- keep the frontend API base URL unset so same-origin `/api` is used.

If the API lives on a different host, configure `window.LATEXED_API_BASE_URL` or the `latexed-api-base-url` meta tag.

When `DEBUG=false`, FastAPI also applies Trusted Host validation from `ALLOWED_HOSTS`. The development default is permissive so local tools and `TestClient` continue to work, but production deployments should set this list to the exact public hostnames served by the reverse proxy.

If the browser shows a failed `OPTIONS /api/health` preflight, check that the frontend origin is allowed by `CORS_ORIGINS` or `CORS_ORIGIN_REGEX`. Local development defaults allow `localhost`, `127.0.0.1`, and `0.0.0.0` on any port.

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Liveness check: backend process is responding |
| GET | `/api/ready` | Readiness check: database, compiler, LaTeX packages, runtime artifact directories, transcription runtime, and generation worker backlog/stale jobs |
| GET | `/api/transcription/status` | Transcription runtime diagnostics for the configured provider and optional dependencies |
| GET | `/api/projects/` | List projects |
| POST | `/api/projects/` | Create project |
| GET | `/api/projects/{id}` | Get project details |
| PUT | `/api/projects/{id}` | Update project |
| DELETE | `/api/projects/{id}` | Delete project |
| GET | `/api/pupils/` | List pupils in the current placeholder teacher scope |
| POST | `/api/pupils/` | Create a pupil |
| GET | `/api/pupils/{id}` | Get a pupil |
| PATCH | `/api/pupils/{id}` | Update a pupil |
| DELETE | `/api/pupils/{id}` | Delete a pupil and its lessons |
| GET | `/api/lessons/` | List lessons, optionally filtered by `pupil_id`, `date_from`, and `date_to` |
| POST | `/api/lessons/` | Create a lesson for a pupil |
| GET | `/api/lessons/{id}` | Get a lesson |
| PATCH | `/api/lessons/{id}` | Update a lesson topic, date, or status |
| DELETE | `/api/lessons/{id}` | Delete a lesson |
| POST | `/api/lessons/{id}/recordings` | Upload a validated audio recording for a lesson into the trusted lesson artifact root |
| POST | `/api/lessons/{id}/transcribe` | Create a transcript record for a lesson recording through the configured transcription provider |
| GET | `/api/lessons/{id}/transcripts` | List raw/reviewed transcript records for a lesson |
| GET | `/api/lessons/{id}/transcripts/{transcript_id}` | Fetch one transcript in lesson scope |
| PATCH | `/api/lessons/{id}/transcripts/{transcript_id}` | Save reviewed transcript text while preserving the raw transcription output |
| POST | `/api/lessons/{id}/documents/generate` | Generate checklist and mistakes-review `.tex` artifacts from a completed transcript; unreviewed transcripts require `allow_unreviewed=true` and produce draft documents with provenance metadata |
| GET | `/api/lessons/{id}/documents` | List generated lesson documents |
| GET | `/api/lessons/{id}/documents/{document_id}/download` | Download a generated document that belongs to the scoped lesson |
| POST | `/api/lessons/{id}/processing-jobs` | Start a lesson processing job (`full_pipeline`, `transcribe`, or `generate_documents`) and persist status |
| GET | `/api/lessons/{id}/processing-jobs` | List processing jobs for a lesson |
| GET | `/api/lessons/{id}/processing-jobs/{job_id}` | Poll a processing job status |
| POST | `/api/projects/{id}/duplicate` | Duplicate project |
| GET | `/api/files/project/{id}` | List files |
| POST | `/api/files/project/{id}` | Create file |
| PUT | `/api/files/{id}` | Update file |
| DELETE | `/api/files/{id}` | Delete file |
| POST | `/api/compile/` | Compile a project payload |
| POST | `/api/compile/raw` | Compile raw LaTeX JSON payload |
| GET | `/api/compile/history/project/{id}` | Compile history for a project |
| GET | `/api/compile/history/item/{id}` | Compile history item details |
| GET | `/api/compile/download/{filename}` | Download compiled PDF |
| POST | `/api/export/pdf` | Export to PDF |
| POST | `/api/export/html` | Export to HTML |
| POST | `/api/export/tex` | Export to TEX ZIP |
| GET | `/api/export/download/{filename}` | Download exported file |
| GET | `/api/templates/` | List templates |
| GET | `/api/templates/{id}` | Get template details |
| GET | `/api/generation/presets` | List generation presets |
| POST | `/api/generation/prompt` | Preview the AI LaTeX generation prompt |
| GET | `/api/generation/providers/status` | Check selected Ollama or OpenAI-compatible provider/model availability |
| POST | `/api/generation/validate` | Validate generated or edited LaTeX structure before compile |
| POST | `/api/generation/generate` | Generate LaTeX through Ollama or an OpenAI-compatible vendor |
| POST | `/api/generation/jobs` | Create/run a durable generation job; supports the configured idempotency header for safe client retries |
| GET | `/api/generation/jobs` | List current-owner generation jobs with optional `project_id`, `status`, `skip`, and `limit` filters |
| GET | `/api/generation/jobs/{id}` | Poll a generation job in the current owner scope |
| POST | `/api/generation/jobs/{id}/retry` | Retry a failed or canceled generation job using its stored request payload |
| POST | `/api/generation/jobs/{id}/cancel` | Cancel a queued/running generation job in the current owner scope |
| GET | `/api/generation/jobs/operator/status` | Owner-scoped operator summary with job counts, backlog and stale job samples without prompts/materials |
| POST | `/api/generation/jobs/operator/recover-stale` | Owner-scoped stale-running job recovery trigger |

Deprecated compatibility routes are still available for compile history:

- `GET /api/compile/history/{project_id}`
- `GET /api/compile/history/detail/{history_id}`

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///./latexed.db` | Database connection string |
| `AUTO_CREATE_TABLES` | `true` | Create SQLAlchemy tables on app startup for local/dev convenience; set `false` in production and use Alembic migrations |
| `DEBUG` | `false` | Debug mode |
| `SECRET_KEY` | `change-me-in-production-please` | Secret key for JWT/session-related features |
| `LOCAL_USER_ID` | `local-teacher` | Local single-user fallback identity used when no trusted user header is present |
| `TRUSTED_USER_HEADER` | `X-Latexed-User` | Header name populated by a trusted auth proxy with the current user id; blank/control-character values are rejected |
| `ALLOWED_HOSTS` | `["*"]` | Trusted host allowlist used when `DEBUG=false`; override with exact public/reverse-proxy hostnames in production |
| `LATEX_COMPILER` | `pdflatex` | LaTeX compiler binary |
| `COMPILE_TIMEOUT` | `30` | Compilation timeout in seconds |
| `COMPILE_WORK_DIR` | `/tmp/latexed_compiles` | Temporary compile/PDF artifact directory |
| `MAX_LATEX_FILES` | `100` | Maximum number of LaTeX project files accepted by compile/export payloads; set `0` to disable |
| `MAX_LATEX_FILE_CHARS` | `500000` | Maximum characters allowed in a single LaTeX file for compile/export payloads; set `0` to disable |
| `MAX_LATEX_TOTAL_CHARS` | `2000000` | Maximum total characters allowed across a compile/export payload; set `0` to disable |
| `MAX_COMPILER_OUTPUT_CHARS` | `20000` | Maximum compiler output/log characters returned through API responses/history; set `0` to disable truncation |
| `LATEX_ALLOWED_EXTENSIONS` | `.tex,.bib,.cls,.sty` | Comma-separated allowlist for user-provided LaTeX project files accepted by compile/export payloads |
| `ARTIFACT_TTL_SECONDS` | `86400` | Best-effort cleanup threshold for trusted compile/export/lesson artifacts; set `0` to disable automatic cleanup |
| `UPLOAD_DIR` | `/tmp/latexed_uploads` | Upload/export artifact directory |
| `LESSON_ARTIFACT_ROOT` | empty (`${UPLOAD_DIR}/lessons`) | Trusted root for lesson audio artifacts; leave empty to derive from `UPLOAD_DIR` |
| `MAX_LESSON_AUDIO_SIZE` | `104857600` | Maximum lesson audio upload size in bytes |
| `LESSON_AUDIO_ALLOWED_CONTENT_TYPES` | `audio/webm,audio/wav,audio/mpeg,audio/mp4,audio/ogg,audio/x-m4a` | Comma-separated allowlist for lesson audio upload media types |
| `LESSON_AUDIO_ALLOWED_EXTENSIONS` | `.webm,.wav,.mp3,.m4a,.ogg` | Comma-separated allowlist for lesson audio upload filename extensions |
| `LESSON_AUDIO_DURATION_PROBE_ENABLED` | `true` | Enable best-effort `ffprobe` duration metadata for stored lesson audio when `ffprobe` is available |
| `MAX_LESSON_AUDIO_DURATION_SECONDS` | `0` | Maximum probed audio duration; `0` disables duration rejection |
| `LESSON_JOB_EXECUTION_MODE` | `inline` | Lesson job execution mode: `inline` preserves current synchronous behavior; `background` returns queued jobs and schedules in-process background execution |
| `TRANSCRIPTION_PROVIDER` | `disabled` | Transcription provider selector (`disabled`, `fake`, `faster_whisper`, or `legacy_whisper`/`whisper`) |
| `TRANSCRIPTION_LANGUAGE` | `ru` | Default transcription language |
| `TRANSCRIPTION_MODEL` | `small` | Whisper/faster-whisper model name when an optional adapter is enabled |
| `TRANSCRIPTION_BEAM_SIZE` | `5` | Beam size for Whisper/faster-whisper adapters |
| `TRANSCRIPTION_DEVICE` | `cpu` | Device passed to the optional faster-whisper adapter |
| `TRANSCRIPTION_COMPUTE_TYPE` | `int8` | Compute type passed to the optional faster-whisper adapter |
| `TRANSCRIPTION_WORD_TIMESTAMPS` | `false` | Enable word timestamps in the optional faster-whisper adapter |
| `LESSON_DOCUMENT_PROVIDER` | `fake` | Lesson document provider selector; currently `fake` or disabled fallback |
| `LESSON_DOCUMENT_ALLOWED_TYPES` | `check_list,pupil_mistakes` | Comma-separated document types planned for lesson generation |
| `CORS_ORIGINS` | local dev origins | Explicit allowed CORS origins |
| `CORS_ORIGIN_REGEX` | local `localhost`/`127.0.0.1`/`0.0.0.0` ports | Regex for local-development frontend origins; set to an empty value or stricter regex in production |
| `AI_PROVIDER` | `ollama` | Default generation provider (`ollama`, `vendor`, or `openai_compatible`) |
| `AI_GENERATION_TIMEOUT` | `120` | AI generation request timeout in seconds; increase for slow local Ollama models such as 14B+ |
| `AI_GENERATION_JOB_EXECUTION_MODE` | `inline` | Persisted generation job execution mode: `inline` runs before returning; `background` schedules in-process background execution; `external` leaves jobs queued for a separate worker/queue adapter |
| `AI_GENERATION_JOB_TIMEOUT_SECONDS` | `0` | Optional timeout for persisted generation jobs; `0` disables timeout failure marking |
| `AI_GENERATION_JOB_STALE_AFTER_SECONDS` | `0` | Optional stale-running job recovery threshold based on worker heartbeat/`updated_at`; `0` disables automatic recovery |
| `AI_PROVIDER_STATUS_TIMEOUT` | `10` | Short timeout for provider/model availability checks |
| `AI_RATE_LIMIT_PER_MINUTE` | `20` | Per-client per-endpoint limit for AI endpoints; set `0` to disable |
| `AI_REQUEST_CONTROL_BACKEND` | `memory` | Request-control backend for AI rate limits and duplicate guards: `memory` for single-process/local, `redis` for shared state across API replicas |
| `AI_REQUEST_CONTROL_REDIS_URL` | unset | Redis connection URL required when `AI_REQUEST_CONTROL_BACKEND=redis` |
| `AI_REQUEST_CONTROL_REDIS_PREFIX` | `latexed:ai_request_control` | Redis key prefix for AI request-control rate-limit and in-flight keys |
| `AI_IN_FLIGHT_TTL_SECONDS` | `300` | Redis duplicate-submit guard TTL; prevents stuck in-flight keys if an API replica dies before cleanup |
| `AI_DUPLICATE_RETRY_AFTER_SECONDS` | `3` | Retry hint returned when an identical generation request is already in flight |
| `AI_IDEMPOTENCY_HEADER` | `Idempotency-Key` | Header accepted by `POST /api/generation/jobs` to replay the same persisted job for safe client retries |
| `AI_IDEMPOTENCY_KEY_MAX_CHARS` | `128` | Maximum idempotency key length; keys may contain ASCII letters/digits plus `.`, `_`, `:`, and `-` |
| `AI_MAX_MATERIALS_CHARS` | `50000` | Maximum size of user materials accepted by AI prompt/generate endpoints |
| `AI_MAX_PROMPT_CHARS` | `200000` | Maximum generated prompt size before a provider call is allowed |
| `AI_MAX_RAW_OUTPUT_CHARS` | `200000` | Maximum provider raw output / LaTeX validation payload size |
| `AI_EXPOSE_PROVIDER_ERRORS` | `false` | Expose upstream provider error details to clients; keep `false` in production |
| `AI_COMPILE_CHECK_ENABLED` | `true` | Run a best-effort backend compile check after AI generation when `pdflatex` is available |
| `AI_REPAIR_ATTEMPTS` | `1` | Maximum automatic AI repair attempts after a generated LaTeX document fails the compile check |
| `LOG_LEVEL` | `INFO` | Backend log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `LOG_FORMAT` | timestamped text format | Python logging format; includes `request_id` by default |
| `LOG_SLOW_REQUEST_MS` | `1000` | Requests at or above this duration are logged as warnings |
| `AI_LOG_PROMPT_PREVIEW_CHARS` | `500` | Max compact prompt preview characters in AI logs; set `0` to disable previews |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `qwen2.5:3b` | Default Ollama model for LaTeX generation |
| `AI_VENDOR_BASE_URL` | `https://api.openai.com/v1` | OpenAI-compatible vendor API base URL |
| `AI_VENDOR_API_KEY` | empty | API key for vendor generation |
| `AI_VENDOR_MODEL` | `gpt-4o-mini` | Default OpenAI-compatible vendor model |
| `AI_VENDOR_TEMPERATURE` | `0.2` | Vendor generation temperature |

Generation jobs are durable even in `inline` mode: every `POST /api/generation/jobs` stores a job row before provider execution. Set `AI_GENERATION_JOB_EXECUTION_MODE=background` to return queued jobs immediately and run provider work through FastAPI background tasks; this is suitable for local/dev. Set `AI_GENERATION_JOB_EXECUTION_MODE=external` when a deployment has a separate worker/queue adapter: the API persists a queued job and returns immediately, while the external worker claims queued rows and runs them through the same `GenerationJobService`/`GenerationOrchestrator` boundary. Run `make generation-worker` for a continuous worker loop or `make generation-worker-once` for a one-shot claim/run cycle; both call `backend/scripts/run_generation_jobs.py`, which also supports `--job-id`, `--owner-id`, `--max-jobs`, `--poll-interval-seconds`, `--timeout-seconds`, `--recover-stale`, `--recover-stale-only`, and `--stale-after-seconds`. Configure `AI_GENERATION_JOB_STALE_AFTER_SECONDS` (or pass `--stale-after-seconds`) to requeue `running` jobs whose worker heartbeat is older than the threshold; leave it at `0` to disable automatic stale recovery. `/api/ready` includes a `generation_jobs` check with queued/running/completed/failed/canceled counts, backlog, stale-running count, execution mode, and stale threshold so operators can see worker pressure before starting recovery. For a more detailed owner-scoped operator view, use `GET /api/generation/jobs/operator/status`; it returns counts and stale job samples containing IDs/timestamps only, never full prompts/materials. Use `POST /api/generation/jobs/operator/recover-stale` to requeue stale running jobs for the current owner. Job responses include operational timing metrics (`queue_wait_seconds`, `run_duration_seconds`, and `total_duration_seconds`) so operators can distinguish queue delay from provider/compile runtime. Use `GET /api/generation/jobs` for an operator-safe list of current-owner jobs, `POST /api/generation/jobs/{id}/retry` to rerun failed/canceled jobs from stored request metadata, `POST /api/generation/jobs/{id}/cancel` to mark queued/running jobs as canceled, and set `AI_GENERATION_JOB_TIMEOUT_SECONDS` when a deployment needs persisted timeout failures for slow or stuck provider calls. The frontend generation modal includes a lightweight “История jobs” panel backed by `GET /api/generation/jobs` for recent current-project job diagnostics.

Lesson document generation records provenance for each artifact: provider, prompt hash, source transcript hash, and whether raw or edited transcript text was used. Reviewed transcripts produce `completed` documents; raw/unreviewed transcripts must be explicitly confirmed with `allow_unreviewed=true` and produce `draft` documents so teachers can distinguish generated materials that still need review.

Optional local transcription runtime requires installing `faster-whisper` in the deployment image or virtualenv before setting `TRANSCRIPTION_PROVIDER=faster_whisper`. Install it with `uv sync --group transcription` or `uv pip install faster-whisper==1.2.1`, and make sure system `ffmpeg` and `ffprobe` are on `PATH`. The legacy `TRANSCRIPTION_PROVIDER=legacy_whisper` adapter requires `uv sync --group legacy-transcription` or `uv pip install openai-whisper==20250625`, plus system `ffmpeg`/`ffprobe` and the repository `transcribe.py` adapter. The default `disabled` and CI `fake` providers do not require model downloads, ffmpeg, or faster-whisper. Use `GET /api/transcription/status` or the `transcription` section of `GET /api/ready` before enabling lesson transcription in a deployment; missing optional packages or media binaries are reported with `missing_requirements` and an `install_hint`. If `/api/lessons/{id}/transcribe` logs `provider=disabled` or returns a failed transcript with `Transcription provider is disabled`, the backend is running in the safe no-provider mode; set `TRANSCRIPTION_PROVIDER=faster_whisper` after installing the optional runtime, or set `TRANSCRIPTION_PROVIDER=fake` only for local UI smoke tests.

## Logging and observability

The backend writes structured text logs to stdout/stderr so they are visible in local terminals, Docker logs and process managers.

What is logged:

- every HTTP request start/completion with method, path, status, duration, client and `X-Request-ID`;
- slow requests as warnings based on `LOG_SLOW_REQUEST_MS`;
- AI prompt preview/generation events with provider, model, topic, lengths, estimated input/output token counts, SHA-256 short digests and validation counts;
- provider status checks and provider HTTP failures without logging API keys;
- rate-limit and payload-limit rejections for AI endpoints.

Useful local commands:

```bash
make backend
make docker-logs
```

To correlate a browser/API call with backend logs, pass or inspect `X-Request-ID`; the backend echoes it in the response and includes it in log lines.

## Manual AI generation smoke test

Use this checklist to verify the complete generation path manually after the backend and frontend are running.

### Prerequisites

- Run `make sync` once to install Python dependencies.
- Start the backend in one terminal with `make backend`.
- Start the frontend in another terminal with `make frontend`.
- Open http://localhost:8080/main.html.
- For server-side PDF compilation, ensure `pdflatex` is installed and available on `PATH`.
- For Russian generated PDFs (`\usepackage[russian]{babel}` and T2A), install Cyrillic TeX Live support. On Ubuntu/Debian:

  ```bash
  sudo apt install texlive-latex-base texlive-latex-extra texlive-lang-cyrillic
  make latex-check
  ```

### Option A: local Ollama

1. Install and start Ollama.
2. Pull the configured model, for example:

   ```bash
   ollama pull qwen2.5:3b
   ```

3. Check that the backend can reach Ollama:

   ```bash
   make ai-provider-status AI_PROVIDER=ollama AI_MODEL=qwen2.5:3b
   ```

4. In the browser, click **AI** → **Проверить провайдера**. The status should say that Ollama is reachable and the model is available.

### Option B: OpenAI-compatible vendor

1. Export vendor settings before starting the backend:

   ```bash
   export AI_PROVIDER=vendor
   export AI_VENDOR_BASE_URL=https://api.openai.com/v1
   export AI_VENDOR_API_KEY=your_api_key_here
   export AI_VENDOR_MODEL=gpt-4o-mini
   make backend
   ```

2. Check provider status:

   ```bash
   make ai-provider-status AI_PROVIDER=vendor AI_MODEL=gpt-4o-mini
   ```

3. In the browser, select **Vendor / OpenAI-compatible**, set the model, and click **Проверить провайдера**.

### Browser end-to-end checklist

1. Confirm the status bar shows that the backend is online, or verify `make health` succeeds.
2. Click **AI** in the header.
3. Fill at least **Тема**; optionally fill **ФИО ученика** and **Материалы / условия задач**.
4. Choose **Язык пособия**, **Источник содержания**, and **Режим LaTeX**:
   - **Только по материалам пользователя** keeps generation grounded in the supplied materials and marks missing data instead of inventing it;
   - **Разрешить нейросети генерировать от себя** lets the model create theory, examples, practice tasks, and answers from the selected topic/level/class;
   - **Safe** maximizes compile success by avoiding or simplifying risky visual/table constructs, while **Rich** allows more complex LaTeX when you are ready to review/repair it.
5. Click **Проверить prompt** and confirm the prompt preview status is successful.
6. Click **Проверить провайдера** and confirm the selected provider/model is available.
7. Choose where to place the result: create a new `generated.tex`, replace the active file, or append to the active file.
8. Click **Сгенерировать и вставить**.
9. If structural validation or `compile_check` fails, use the modal's **Повторить repair**, **Перегенерировать safe**, or **Перегенерировать rich** actions; use **Вставить всё равно** only when you intentionally want to inspect/fix the returned source manually.
10. Confirm generated LaTeX appears in the selected target and begins with `\documentclass`; the backend now wraps the model's body-only answer with the fixed Latexed preamble (Russian/T2A, math, tables, TikZ/pgfplots, typography, blocks, and hyperref/tcolorbox packages).
11. Click **Проверить .tex** if you want to validate the current editor content again.
12. Compile with **Компиляция** or `Ctrl+Enter`.
13. Confirm the response includes `compile_check` and `token_usage`; `token_usage.input_tokens` and `token_usage.output_tokens` are deterministic estimates for the prompt/repair inputs and provider outputs used to produce one valid пособие. When `pdflatex` is available, the backend normalizes common model LaTeX body mistakes, escapes common text-only special characters, deterministically simplifies risky Safe-mode fragments, validates environment/math/braces/math-mode balance and safe-mode restrictions, attempts to compile generated LaTeX and performs one automatic repair attempt before returning the final code. Confirm the PDF preview loads after insertion, or review the compile error panel if LaTeX still needs correction.
14. Right-click the generated file in the file tree and choose **Исследовать AI-документ** to review the prompt (or stored prompt preview), AI run count, token totals, provider/model, validation and compile-check metadata.
15. If a `project_id` was sent, inspect generation history through `/api/generation/history/project/{project_id}`; history stores bounded prompt/LaTeX previews plus hashes/metadata and token totals, not full raw provider output.
16. Exercise exports through **Экспорт** → PDF, HTML, and `.tex` archive.

### API-only smoke commands

These commands are useful when debugging without the browser:

```bash
make health
make ai-provider-status AI_PROVIDER=ollama AI_MODEL=qwen2.5:3b
make ai-validate-smoke
make clean-artifacts   # optional: remove local generated PDFs/exports in default /tmp artifact dirs
curl -fsS -X POST http://localhost:8000/api/generation/prompt \
  -H 'Content-Type: application/json' \
  --data '{"provider":"ollama","model":"qwen2.5:3b","fields":{"topic":"Показательные уравнения","student_name":"Михаил Романов","language":"русский","content_source_mode":"materials_only","latex_mode":"safe"},"materials":"Решить уравнение 2^x = 8."}'
curl -fsS http://localhost:8000/api/generation/history/project/YOUR_PROJECT_ID
```

If generation fails, check provider status first, then inspect backend logs for provider errors, timeout messages, or missing API key/model configuration.

For local Ollama timeouts (`ReadTimeout` / HTTP 504), first run `ollama list` and `ollama pull <model>`, then try a smaller model or increase `AI_GENERATION_TIMEOUT` before restarting the backend. Large models can exceed 120 seconds on CPU-only or low-memory machines.

## Testing

Install dependencies first:

```bash
make sync
```

Run all local checks:

```bash
make check
```

Individual checks:

```bash
make compileall
make frontend-check
make test
```

Direct `uv` test invocation from the repository root also works because `pyproject.toml` configures the backend Python path:

```bash
uv run pytest backend/tests/ -q
```

Frontend syntax smoke check without Make:

```bash
node --check frontend/js/*.js
```

## Known limitations

- Frontend CSS and JavaScript are split out of `frontend/main.html`, and application JavaScript is grouped into ordered scripts under `frontend/js/`. A future cleanup can migrate these classic scripts to ES modules or TypeScript once a build step is introduced.
- Local preview is an approximate HTML/KaTeX rendering path; authoritative PDF output comes from the backend LaTeX compiler.
- Server-side compile/export requires a working LaTeX installation. Without `pdflatex`, compile endpoints return errors while the frontend can still use local preview fallback.
- Generated Russian documents require `russian.ldf`/T2A support from `texlive-lang-cyrillic`; otherwise `babel` may fail with `Unknown option 'russian'`.

## License

MIT
