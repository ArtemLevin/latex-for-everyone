# AI Agent Guidelines for Latexed

## Project overview

Latexed is an online LaTeX editor with:

- a FastAPI backend under `backend/app/`;
- a single-page browser frontend under `frontend/`;
- SQLAlchemy persistence for projects, files, compile history, and snapshots;
- server-side LaTeX compilation/export through `pdflatex`;
- local frontend preview fallback with CodeMirror and KaTeX;
- AI-assisted LaTeX generation, prompt preview, provider status checks, and structural LaTeX validation.

This repository is **not** the booking-calendar example that older docs referenced. Treat any booking-domain examples as stale and replace them with Latexed-specific terminology.

## Quick start for agents

1. Verify the real repository layout before assuming paths.
2. Identify the layer and feature area: frontend UI, API router, service, persistence model, migration, test, or documentation.
3. Follow `Explore → Plan → Code → Verify` in small increments.
4. Run the checks that exist in this repository and document any environment limitations.
5. Keep the final diff focused; do not mix unrelated refactors with feature changes.

## Verify first

Run this before path-based work:

```bash
rg --files | head -n 80
for p in backend/app backend/tests backend/alembic frontend docs; do
  if [ -d "$p" ]; then
    echo "OK: $p/"
  else
    echo "MISSING: $p/"
  fi
done
```

Expected top-level structure:

```text
backend/            FastAPI application, tests, Alembic scaffold, Docker/Nginx config
backend/app/        Python package for API, models, schemas, services, worker, websockets
backend/tests/      pytest tests for backend behavior
backend/alembic/    Alembic migration environment
frontend/main.html  Single-page editor UI markup
frontend/css/       Frontend styles
frontend/js/        Ordered browser scripts for state, API, editor, compile/export, AI, settings
docs/               Project documentation for agents and maintainers
```

## Commands

Use the actual Makefile targets:

```bash
make sync             # Install/update uv environment with app and dev dependencies
make backend          # Run FastAPI backend on BACKEND_PORT (default: 8000)
make frontend         # Serve frontend/main.html on FRONTEND_PORT (default: 8080)
make open             # Print useful local URLs
make health           # Call GET /api/health on the running backend
make test             # Run backend pytest suite
make compileall       # Compile backend Python files for syntax errors
make frontend-check   # Run node --check for frontend JavaScript files
make check            # Run compileall, frontend-check, and test
make latex-check      # Check local pdflatex + Russian babel/T2A support
make migrate          # Run Alembic migrations
make migration MSG="message"  # Create an Alembic autogeneration revision
```

There are currently no `make lint` or `make typecheck` targets. If a task asks for lint/typecheck, either add the target intentionally or report that the repository does not define it.

## Architecture rules

### Current architecture

The current codebase is a pragmatic FastAPI application:

```text
FastAPI app (`backend/app/main.py`)
  → routers (`backend/app/routers/*.py`)
  → services (`backend/app/services/*.py`) for LaTeX, PDF, AI, prompt, validation concerns
  → SQLAlchemy models/session (`backend/app/models.py`, `backend/app/database.py`)
  → Pydantic schemas (`backend/app/schemas.py`) for API/service boundaries
```

Some routers still access SQLAlchemy sessions directly. Treat this as **existing legacy**, not a pattern to expand.

### Target direction for new backend work

For new or substantially changed backend behavior, prefer:

```text
Router → Service → Database/session/model
```

- Routers should focus on HTTP details: request/response models, dependency wiring, status codes, and translating known service errors to HTTP errors.
- Services should own business and integration logic: LaTeX compilation orchestration, PDF export rules, AI provider interaction, validation, persistence workflows.
- Models should remain persistence-only and must not perform HTTP calls, file-system side effects, subprocess calls, or AI provider calls.
- Schemas in `backend/app/schemas.py` are the canonical API contracts; search before creating new ones.

Do **not** introduce a repository layer unless the change clearly benefits from it. If you do, keep it small and avoid rewriting unrelated routers.

### Feature ownership

- Projects/files/snapshots: `backend/app/routers/projects.py`, `backend/app/routers/files.py`, `backend/app/models.py`, `backend/app/schemas.py`.
- Compilation: `backend/app/routers/compile.py`, `backend/app/services/latex_compiler.py`, `backend/app/services/latex_sanitizer.py`.
- Export: `backend/app/routers/export.py`, `backend/app/services/pdf_generator.py`.
- AI generation: `backend/app/routers/generation.py`, `backend/app/services/ai_generation.py`, `backend/app/services/prompt_builder.py`, `backend/app/services/latex_validator.py`.
- Frontend startup/API/editor: `frontend/js/01-state.js`, `frontend/js/02-api.js`, `frontend/js/03-init.js`.
- Frontend file tree: `frontend/js/04-files.js`.
- Frontend compile/preview: `frontend/js/05-compile-preview.js`.
- Frontend toolbar/view/settings: `frontend/js/06-toolbar-view.js`, `frontend/js/09-ui-settings.js`.
- Frontend AI/templates/export: `frontend/js/07-generation.js`, `frontend/js/08-templates-export.js`.

## Code style

### Python

- Use type annotations for new functions and meaningful return types.
- Keep imports grouped: standard library, third-party, first-party.
- Reuse existing Pydantic models from `backend/app/schemas.py` where possible.
- Avoid `Any` unless the data is truly unstructured JSON or the existing schema already requires it.
- Keep functions focused; extract helpers for non-trivial LaTeX, export, AI, or persistence logic.
- Do not wrap imports in `try/except`.
- Avoid logging sensitive content. For AI prompts/LaTeX content, prefer lengths, hashes, or short previews governed by settings.

### JavaScript/frontend

- Preserve the script ordering from `frontend/main.html`; files depend on globals loaded earlier.
- Keep browser code dependency-free unless a library is already loaded by `main.html`.
- Use the existing `apiRequest`, `showToast`, modal, and status helper patterns.
- If backend is optional for a flow, preserve or add a local/offline fallback where appropriate.
- Run `make frontend-check` after changing `frontend/js/*.js`.
- If a perceptible UI change is made, run the app and take a screenshot when possible.

### LaTeX-specific safety

- Preserve filename/path sanitization for compile/export flows.
- Never allow user-provided absolute paths, parent directory traversal, or external URLs to be passed to compiler file operations.
- Keep compile timeouts and bounded output handling.
- Prefer structural validation before inserting AI-generated LaTeX into user files.
- Maintain Russian LaTeX support expectations (`babel` with Russian, T2A/fontenc where relevant) and document environment limitations.

## Testing rules

- Add or update tests for changed backend behavior in `backend/tests/`.
- For service behavior, test happy path, edge/error path, and known LaTeX/AI/provider failure modes where practical.
- For router changes, prefer `TestClient` integration tests matching the current test style.
- For frontend JavaScript changes, at minimum run `make frontend-check`; add targeted browser/manual notes for UI behavior if automated tests do not exist.
- When changing compile/export code, consider whether `pdflatex` availability affects the test. If the environment lacks TeX Live, document it as an environment limitation rather than hiding failures.

## Database and migrations

- Models live in `backend/app/models.py`.
- The app currently calls `Base.metadata.create_all(bind=engine)` at startup; Alembic scaffolding exists under `backend/alembic/` for migration workflows.
- For schema changes, add an Alembic migration via `make migration MSG="..."` when autogeneration is viable, review it carefully, then run `make migrate` if the environment supports it.
- Do not delete or rewrite local `.db` files unless the task explicitly requires cleanup.

## Documentation rules

Update documentation when changing:

- public API paths, request/response schemas, or error behavior;
- frontend/backend integration behavior;
- AI generation prompt fields, provider configuration, validation, or insertion modes;
- compile/export prerequisites, limitations, or operational workflow;
- Makefile commands or setup steps.

Keep examples Latexed-specific. Do not add booking/calendar examples.

## Agent workflow

### Explore

- Inspect related routers, services, schemas, tests, and frontend call sites.
- Search existing schemas/helpers before creating new ones.
- Verify whether docs or README already describe the behavior.

### Plan

- State the intended layer(s) and files.
- Identify compatibility risks for frontend/API clients.
- Decide which tests/checks are relevant.

### Code

- Make small focused edits.
- Preserve existing public contracts unless the task explicitly changes them.
- Avoid unrelated formatting churn.

### Verify

Prefer this order after changes:

```bash
make frontend-check    # if frontend JS changed
make compileall        # if Python changed
make test              # if backend behavior changed
make check             # when broad confidence is needed and dependencies are available
```

If `uv` cannot download dependencies or `pdflatex` is missing, report the exact command and failure as an environment limitation.

## Safety rules

- Never commit secrets, API keys, tokens, PDFs with sensitive content, or local databases.
- Never run destructive commands such as `rm -rf` or database drops unless the user explicitly requested them.
- Never delete files without confirmation unless you created them during the current task and they are clearly temporary.
- Do not expose full prompts, source documents, or LaTeX content in logs/errors when it may contain user data.

## Definition of Done

- [ ] Change matches the requested Latexed scope.
- [ ] Existing docs/examples are not stale booking-domain content for touched areas.
- [ ] Public schemas/API behavior are preserved or intentionally documented.
- [ ] Relevant tests/checks were run, or limitations are clearly documented.
- [ ] No secrets, debug code, local DB artifacts, generated PDFs, or unrelated formatting churn are included.
- [ ] Final response cites changed files and lists exact verification commands.
