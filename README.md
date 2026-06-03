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
frontend/main.html  Browser editor UI and backend API client
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
| `make test` | Run backend tests with `uv`. |
| `make frontend-check` | Extract inline frontend JavaScript and run `node --check`. |
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
```

## uv notes

- `pyproject.toml` is the source for `uv sync` and includes runtime dependencies plus a `dev` dependency group for tests.
- The project is configured with `package = false`, so `uv` manages the environment without requiring this repository to be installed as a Python package.
- Backend commands run from `backend/` so `app.main:app` imports resolve the same way they do with plain `uvicorn`.
- `requirements.txt` remains available for Docker and pip-based workflows.

## Frontend/backend integration

`frontend/main.html` contains a small API client. On startup it:

1. calls `GET /api/health`;
2. loads a saved project from `localStorage` or creates a new one with the `article` template;
3. loads project files from `GET /api/files/project/{project_id}`;
4. loads templates from `GET /api/templates/`;
5. autosaves the current file with `PUT /api/files/{file_id}`;
6. compiles with `POST /api/compile/` and embeds returned PDFs with `/api/compile/download/{filename}`;
7. exports through `/api/export/pdf`, `/api/export/html`, and `/api/export/tex` when the backend is online;
8. opens the AI generation dialog, can check the selected AI provider/model, sends prompt fields to `/api/generation/generate`, validates returned `latex_code`, inserts it into the active `.tex` file, saves it, and starts compilation.

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
| `LATEX_COMPILER` | `pdflatex` | LaTeX compiler binary |
| `COMPILE_TIMEOUT` | `30` | Compilation timeout in seconds |
| `COMPILE_WORK_DIR` | `/tmp/latexed_compiles` | Temporary compile/PDF artifact directory |
| `UPLOAD_DIR` | `/tmp/latexed_uploads` | Upload/export artifact directory |
| `CORS_ORIGINS` | `['http://localhost:3000', 'http://localhost:8080']` | Allowed CORS origins |
| `AI_PROVIDER` | `ollama` | Default generation provider (`ollama`, `vendor`, or `openai_compatible`) |
| `AI_GENERATION_TIMEOUT` | `120` | AI generation request timeout in seconds |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `qwen2.5:14b` | Default Ollama model for LaTeX generation |
| `AI_VENDOR_BASE_URL` | `https://api.openai.com/v1` | OpenAI-compatible vendor API base URL |
| `AI_VENDOR_API_KEY` | empty | API key for vendor generation |
| `AI_VENDOR_MODEL` | `gpt-4o-mini` | Default OpenAI-compatible vendor model |
| `AI_VENDOR_TEMPERATURE` | `0.2` | Vendor generation temperature |

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
python3 - <<'PY'
from pathlib import Path
text = Path('frontend/main.html').read_text()
start = text.rfind('<script>') + len('<script>')
end = text.rfind('</script>')
Path('/tmp/frontend-main.js').write_text(text[start:end])
PY
node --check /tmp/frontend-main.js
```

## Known limitations

- `frontend/main.html` is still a monolithic HTML/CSS/JS file. A future cleanup should split API, state, file operations, compile/export, and UI helpers into separate modules.
- Local preview is an approximate HTML/KaTeX rendering path; authoritative PDF output comes from the backend LaTeX compiler.
- Server-side compile/export requires a working LaTeX installation. Without `pdflatex`, compile endpoints return errors while the frontend can still use local preview fallback.

## License

MIT
