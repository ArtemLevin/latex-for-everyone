# Architecture Boundaries

This document describes the architecture that should guide new work in Latexed. It is intentionally based on the current repository layout, not the stale booking-calendar examples that used to live here.

## Current layout

```text
backend/app/main.py          FastAPI app creation, middleware, router registration, health/root endpoints
backend/app/routers/*.py     HTTP endpoints for projects, files, compile, export, templates, AI generation
backend/app/services/*.py    LaTeX/PDF/AI/prompt/validation logic
backend/app/models.py        SQLAlchemy persistence models
backend/app/schemas.py       Pydantic request/response and service boundary schemas
backend/app/database.py      SQLAlchemy engine/session dependency
frontend/main.html           Single-page editor shell
frontend/js/*.js             Ordered browser scripts loaded by main.html
docs/*.md                    Maintainer and agent documentation
```

## Runtime flow

```text
Browser SPA
  → API helper (`frontend/js/02-api.js`)
  → FastAPI router (`backend/app/routers/*.py`)
  → service when non-trivial behavior is involved (`backend/app/services/*.py`)
  → SQLAlchemy session/model or external tool/provider
```

Compilation and export add file-system/subprocess boundaries:

```text
Compile request
  → compile router
  → LatexCompiler
  → sanitized temporary work directory
  → pdflatex subprocess
  → generated PDF download URL
```

AI generation adds provider and validation boundaries:

```text
Generation request
  → generation router
  → prompt builder
  → AI generation service/provider
  → LaTeX extraction
  → structural validator
  → response/insertion by frontend
```

## Target dependency direction

For new or substantially refactored backend behavior, use:

```text
Router → Service → Database/session/model or external boundary
```

Routers may still perform simple persistence operations in legacy areas, but new complex behavior should move orchestration into services. Project and file routers now delegate CRUD, snapshot, duplicate, upload and main-file invariants to `ProjectService` and `FileService`; keep extending those services instead of adding new database business logic directly to the routers.

### Router responsibilities

Routers should:

- declare HTTP paths, methods, response models, query/body parameters, and dependency injection;
- translate known service errors into `HTTPException` responses;
- avoid logging full user content;
- avoid subprocess, file-system, AI-provider, or heavy business logic.

### Service responsibilities

Services should:

- own non-trivial business/integration behavior;
- sanitize and validate LaTeX content before dangerous boundaries;
- centralize provider and compiler interactions;
- return typed results such as `LatexCompileResult` and `PDFGenerationResult`;
- keep side effects explicit and bounded.

### Model/session responsibilities

Models should:

- represent persisted project, file, compile history, and snapshot state;
- avoid HTTP calls, subprocess calls, file writes, and AI/provider calls;
- keep domain methods simple if any are added.

Schemas should remain the canonical API contracts in `backend/app/schemas.py`.

## Public API contract policies

### Health/root

- `GET /api/health` returns backend status, version, and configured compiler.
- `GET /` returns application metadata and docs location.

### Projects/files

- Projects own files and snapshots.
- File content is user data; avoid echoing it into logs beyond existing explicit API responses.
- Project and file IDs are UUID strings represented as `str` in schemas.

### Compile

- `POST /api/compile/` compiles a project file set and records compile history.
- `POST /api/compile/raw` compiles raw content without a project/history record.
- Compile responses use `status`, `output`, `error`, `compile_time`, `pdf_url`, and optional `history_id`.
- Compile download URLs are backend-generated and should point to files inside the configured compile output directory.

### Export

- Export endpoints support PDF, HTML, and TEX flows.
- Exported filenames and file paths must be sanitized and must not allow path traversal.

### AI generation

- Prompt preview and generation must enforce configured text/rate limits.
- Provider errors should use sanitized messages unless settings explicitly expose provider details.
- Generated LaTeX should be structurally validated before frontend insertion.

### Error payloads

- Missing entities should use `404` with a clear `detail` string.
- Validation errors should use FastAPI/Pydantic `422` payloads.
- External tool/provider failures should not leak sensitive prompts or full document contents.

## Allowed patterns

### Router delegating to a service

```python
@router.post("/validate", response_model=GenerationValidationResponse)
async def validate_generated_latex(request: Request, validation_request: GenerationValidationRequest):
    enforce_ai_rate_limit(request)
    enforce_text_limit("latex_code", validation_request.latex_code, settings.AI_MAX_RAW_OUTPUT_CHARS)
    validation = validate_latex_document(validation_request.latex_code)
    return GenerationValidationResponse(**validation)
```

Why this is acceptable:

- HTTP concerns stay in the router.
- Validation logic is delegated to a service helper.
- The response is typed by an existing schema.

### Typed service boundary

```python
class LatexCompileResult(BaseModel):
    status: Literal["success", "error"]
    output: str | None = None
    error: str | None = None
    compile_time: str | None = None
    pdf_url: str | None = None
```

Why this is acceptable:

- The compiler service and router share a stable typed contract.
- The router does not need to know subprocess details.

### Frontend API helper

```javascript
async function apiRequest(path, options = {}) {
    const response = await fetch(`${API_BASE_URL}${path}`, { ...options });
    if (!response.ok) throw new Error(message);
    return response.json();
}
```

Why this is acceptable:

- Backend URL resolution and error handling are centralized.
- Call sites remain focused on user flow.

## Prohibited patterns

### Direct file paths from user input

```python
# Bad: can write outside the compile work directory.
(work_dir / request.filename).write_text(content)
```

Use `Path(filename).name` or an equivalent allowlist/sanitizer before file-system boundaries.

### Full prompt/document logging

```python
# Bad: may leak user content or copyrighted/private material.
logger.info("prompt=%s latex=%s", prompt, latex_code)
```

Log lengths, hashes, provider/model, status, and bounded previews instead.

### Compiler/provider logic in models

```python
# Bad: persistence model performs side effects.
class File(Base):
    def compile(self):
        subprocess.run(["pdflatex", self.name])
```

Keep these operations in services.

### New duplicate schemas

```python
# Bad: duplicate of an existing response model.
class CompileDTO(BaseModel):
    ...
```

Search `backend/app/schemas.py` first and extend existing contracts deliberately.

## Legacy handling

Existing routers contain direct SQLAlchemy session usage. When touching them:

1. Do not expand direct-DB logic for complex behavior.
2. Move newly complex orchestration into a service when practical.
3. Keep refactors incremental; do not rewrite all routers as a side effect.
4. Add tests around current behavior before changing persistence flows.
5. Document public behavior changes in README/docs.

## Architecture checklist before merge

- [ ] Does the change fit the Latexed domain: projects, files, LaTeX compile/export, AI generation, frontend editor?
- [ ] Are path, compiler, and provider boundaries sanitized and bounded?
- [ ] Are request/response schemas reused or intentionally updated?
- [ ] Are logs safe for user content?
- [ ] Are frontend call sites compatible with API changes?
- [ ] Are tests or explicit manual verification notes included?
