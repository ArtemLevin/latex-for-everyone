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

> Server-side compilation and PDF export require `pdflatex` to be installed and available on `PATH` unless you override `LATEX_COMPILER`.

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
| `make check` | Run Python compile check, frontend syntax check, and backend tests. |
| `make migrate` | Run Alembic migrations. |
| `make migration MSG="..."` | Create an Alembic autogeneration revision. |
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
make ai-provider-status AI_PROVIDER=ollama AI_MODEL=gemma4
```

## uv notes

- `pyproject.toml` is the source for `uv sync` and includes runtime dependencies plus a `dev` dependency group for tests.
- The project is configured with `package = false`, so `uv` manages the environment without requiring this repository to be installed as a Python package.
- Backend commands run from `backend/` so `app.main:app` imports resolve the same way they do with plain `uvicorn`.
- `requirements.txt` remains available for Docker and pip-based workflows.


## Runtime artifacts and cleanup

Latexed creates local runtime files during development and tests. These files are intentionally ignored by git:

- SQLite databases such as `latexed.db`, `test_latexed.db`, `*.sqlite`, and `*.sqlite3`;
- Python/test caches such as `__pycache__/` and `.pytest_cache/`;
- generated compile/export/upload artifacts under the configured runtime directories, for example `/tmp/latexed_compiles` and `/tmp/latexed_uploads`.

Use `make clean` to remove local SQLite databases and Python/test caches from the repository working tree. Generated files under `/tmp` can be removed with normal OS cleanup commands when no backend process is using them. Do not commit local databases, generated PDFs, uploaded user files, `.env` files, or provider credentials.

## Frontend/backend integration

`frontend/main.html` loads `frontend/css/app.css` and ordered scripts from `frontend/js/`; the frontend startup flow:

1. calls `GET /api/health`;
2. loads a saved project from `localStorage` or creates a new one with the `article` template;
3. loads project files from `GET /api/files/project/{project_id}`;
4. loads templates from `GET /api/templates/`;
5. autosaves the current file with `PUT /api/files/{file_id}`;
6. compiles with `POST /api/compile/` and embeds returned PDFs with `/api/compile/download/{filename}`;
7. exports through `/api/export/pdf`, `/api/export/html`, and `/api/export/tex` when the backend is online;
8. opens the AI generation dialog, can check the selected AI provider/model, sends prompt fields to `/api/generation/generate`, validates returned `latex_code`, lets the user choose whether to create a new `.tex`, replace the active file, or append to it, then saves and starts compilation.

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
| GET | `/api/health` | Health check |
| GET | `/api/projects/` | List projects |
| POST | `/api/projects/` | Create project |
| GET | `/api/projects/{id}` | Get project details |
| PUT | `/api/projects/{id}` | Update project |
| DELETE | `/api/projects/{id}` | Delete project |
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

Deprecated compatibility routes are still available for compile history:

- `GET /api/compile/history/{project_id}`
- `GET /api/compile/history/detail/{history_id}`

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///./latexed.db` | Database connection string |
| `DEBUG` | `false` | Debug mode |
| `SECRET_KEY` | `change-me-in-production-please` | Secret key for JWT/session-related features |
| `ALLOWED_HOSTS` | `["*"]` | Trusted host allowlist used when `DEBUG=false`; override with exact public/reverse-proxy hostnames in production |
| `LATEX_COMPILER` | `pdflatex` | LaTeX compiler binary |
| `COMPILE_TIMEOUT` | `30` | Compilation timeout in seconds |
| `COMPILE_WORK_DIR` | `/tmp/latexed_compiles` | Temporary compile/PDF artifact directory |
| `MAX_LATEX_FILES` | `100` | Maximum number of LaTeX project files accepted by compile/export payloads; set `0` to disable |
| `MAX_LATEX_FILE_CHARS` | `500000` | Maximum characters allowed in a single LaTeX file for compile/export payloads; set `0` to disable |
| `MAX_LATEX_TOTAL_CHARS` | `2000000` | Maximum total characters allowed across a compile/export payload; set `0` to disable |
| `UPLOAD_DIR` | `/tmp/latexed_uploads` | Upload/export artifact directory |
| `CORS_ORIGINS` | local dev origins | Explicit allowed CORS origins |
| `CORS_ORIGIN_REGEX` | local `localhost`/`127.0.0.1`/`0.0.0.0` ports | Regex for local-development frontend origins; set to an empty value or stricter regex in production |
| `AI_PROVIDER` | `ollama` | Default generation provider (`ollama`, `vendor`, or `openai_compatible`) |
| `AI_GENERATION_TIMEOUT` | `120` | AI generation request timeout in seconds; increase for slow local Ollama models such as 14B+ |
| `AI_PROVIDER_STATUS_TIMEOUT` | `10` | Short timeout for provider/model availability checks |
| `AI_RATE_LIMIT_PER_MINUTE` | `20` | Per-client per-endpoint in-memory limit for AI endpoints; set `0` to disable |
| `AI_MAX_MATERIALS_CHARS` | `20000` | Maximum size of user materials accepted by AI prompt/generate endpoints |
| `AI_MAX_PROMPT_CHARS` | `60000` | Maximum generated prompt size before a provider call is allowed |
| `AI_MAX_RAW_OUTPUT_CHARS` | `200000` | Maximum provider raw output / LaTeX validation payload size |
| `AI_EXPOSE_PROVIDER_ERRORS` | `false` | Expose upstream provider error details to clients; keep `false` in production |
| `LOG_LEVEL` | `INFO` | Backend log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `LOG_FORMAT` | timestamped text format | Python logging format; includes `request_id` by default |
| `LOG_SLOW_REQUEST_MS` | `1000` | Requests at or above this duration are logged as warnings |
| `AI_LOG_PROMPT_PREVIEW_CHARS` | `500` | Max compact prompt preview characters in AI logs; set `0` to disable previews |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `gemma4` | Default Ollama model for LaTeX generation |
| `AI_VENDOR_BASE_URL` | `https://api.openai.com/v1` | OpenAI-compatible vendor API base URL |
| `AI_VENDOR_API_KEY` | empty | API key for vendor generation |
| `AI_VENDOR_MODEL` | `gpt-4o-mini` | Default OpenAI-compatible vendor model |
| `AI_VENDOR_TEMPERATURE` | `0.2` | Vendor generation temperature |

## Logging and observability

The backend writes structured text logs to stdout/stderr so they are visible in local terminals, Docker logs and process managers.

What is logged:

- every HTTP request start/completion with method, path, status, duration, client and `X-Request-ID`;
- slow requests as warnings based on `LOG_SLOW_REQUEST_MS`;
- AI prompt preview/generation events with provider, model, topic, lengths, SHA-256 short digests and validation counts;
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
   ollama pull gemma4
   ```

3. Check that the backend can reach Ollama:

   ```bash
   make ai-provider-status AI_PROVIDER=ollama AI_MODEL=gemma4
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
4. Choose **Язык пособия** and **Источник содержания**:
   - **Только по материалам пользователя** keeps generation grounded in the supplied materials and marks missing data instead of inventing it;
   - **Разрешить нейросети генерировать от себя** lets the model create theory, examples, practice tasks, and answers from the selected topic/level/class.
5. Click **Проверить prompt** and confirm the prompt preview status is successful.
6. Click **Проверить провайдера** and confirm the selected provider/model is available.
7. Choose where to place the result: create a new `generated.tex`, replace the active file, or append to the active file.
8. Click **Сгенерировать и вставить**.
9. Confirm generated LaTeX appears in the selected target and begins with `\documentclass`.
10. Click **Проверить .tex** if you want to validate the current editor content again.
11. Compile with **Компиляция** or `Ctrl+Enter`.
12. Confirm the PDF preview loads when `pdflatex` is available, or review the compile error panel if LaTeX needs correction.
13. Exercise exports through **Экспорт** → PDF, HTML, and `.tex` archive.

### API-only smoke commands

These commands are useful when debugging without the browser:

```bash
make health
make ai-provider-status AI_PROVIDER=ollama AI_MODEL=gemma4
make ai-validate-smoke
curl -fsS -X POST http://localhost:8000/api/generation/prompt \
  -H 'Content-Type: application/json' \
  --data '{"provider":"ollama","model":"gemma4","fields":{"topic":"Показательные уравнения","student_name":"Михаил Романов","language":"русский","content_source_mode":"materials_only"},"materials":"Решить уравнение 2^x = 8."}'
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
