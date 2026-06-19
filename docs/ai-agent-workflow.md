# AI Agent Workflow Guide

Use this workflow for Latexed changes. It complements `AGENTS.md` and is intentionally specific to this repository.

## Core loop: Explore → Plan → Code → Verify

Do not start from stale assumptions. This repository is a LaTeX editor, not the booking-calendar template that earlier docs referenced.

## Phase 1: Explore

### Verify layout

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

### Find the feature area

Use targeted searches:

```bash
rg -n "@router\.(get|post|put|delete|patch)" backend/app/routers
rg -n "class |def |async def " backend/app/services backend/app/routers
rg -n "apiRequest\(|compileLatex|generateLatex|exportPDF" frontend/js
```

### Read related boundaries

- API behavior: `backend/app/routers/*.py`
- request/response contracts: `backend/app/schemas.py`
- persistence shape: `backend/app/models.py`
- compiler/PDF/AI logic: `backend/app/services/*.py`
- browser flow: `frontend/js/*.js`, loaded in the order declared by `frontend/main.html`
- tests: `backend/tests/test_api.py`

### Explore output

Before coding, know:

- which public endpoint/UI action is affected;
- which schemas or frontend payloads are involved;
- whether user LaTeX content, generated PDFs, or provider responses cross a trust boundary;
- which checks can realistically run in the current environment.

## Phase 2: Plan

Write a short implementation plan for non-trivial changes:

```markdown
## Plan

1. Update [router/service/frontend file] to ...
2. Reuse or extend [schema/helper] for ...
3. Add/update tests in ...
4. Verify with ...

Risks:
- API compatibility: ...
- pdflatex/provider availability: ...
- frontend offline fallback: ...
```

Planning is required for:

- API contract changes;
- DB/model/migration changes;
- compile/export/AI provider behavior;
- broad frontend workflow changes;
- refactors across multiple files.

## Phase 3: Code

### Backend guidelines

- Keep router handlers focused on HTTP-level work.
- Move non-trivial compile/export/AI/persistence orchestration into services.
- Reuse `backend/app/schemas.py` contracts.
- Keep logs safe: no full prompts or full user LaTeX unless explicitly required for a response.
- Preserve compile/export path sanitization and timeouts.

### Frontend guidelines

- Respect script ordering in `frontend/main.html`.
- Use existing global helpers such as `apiRequest`, `showToast`, `setButtonLoading`, and modal helpers.
- Keep local/offline fallback behavior where it already exists.
- Avoid adding a build step unless explicitly requested.

### Documentation guidelines

- Keep examples Latexed-specific.
- Update README/docs when endpoints, commands, environment requirements, AI behavior, or frontend/backend integration changes.
- Remove stale booking/calendar wording when encountered in touched docs.

## Phase 4: Verify

Use the smallest relevant checks first:

```bash
make frontend-check    # frontend/js changes
make compileall        # Python syntax check
make lint              # Ruff lint for backend app/tests
make format-check      # Ruff formatting check for backend app/tests
make test-security     # focused auth/upload/compile/generation regression checks
make test-coverage     # backend coverage report for release/refactor confidence
make test              # backend tests
make check             # broad check when dependencies are available
make latex-check       # TeX Live environment validation when compile/export work depends on it
```

If a check fails because `uv` cannot download dependencies or `pdflatex`/TeX Live is unavailable, record it as an environment limitation with the exact error. Do not mark it as a code failure unless the output proves the patch caused it.

## Common task playbooks

### Add or change an API endpoint

1. Explore the relevant router and frontend call sites.
2. Reuse existing schema or add a clearly named schema in `backend/app/schemas.py`.
3. Put non-trivial logic in a service.
4. Add `TestClient` coverage in `backend/tests/`.
5. Run `make compileall` and `make test`.
6. Update README/docs if the public API changes.

### Change LaTeX compilation

1. Inspect `backend/app/services/latex_compiler.py` and `latex_sanitizer.py`.
2. Preserve temp directory isolation, filename sanitization, timeout handling, and bounded logs.
3. Add tests for sanitizer/error extraction when possible without requiring TeX Live.
4. Run `make compileall`, `make test`, and `make latex-check` if compile environment matters.

### Change AI generation

1. Inspect `backend/app/routers/generation.py`, `ai_generation.py`, `prompt_builder.py`, and `latex_validator.py`.
2. Preserve rate limits, text limits, provider error sanitization, and validation.
3. Avoid logging full prompts or raw model output.
4. Update frontend insertion/status behavior if response shape changes.
5. Run backend checks and `make frontend-check` if UI changed.

### Change frontend UI

1. Inspect `frontend/main.html` for DOM IDs and script load order.
2. Update the smallest JS module responsible for the flow.
3. Run `make frontend-check`.
4. If visual behavior changes, run the app and capture a screenshot when possible.

### Change database shape

1. Update `backend/app/models.py` and schemas if needed.
2. Create/review an Alembic migration with `make migration MSG="..."` when autogeneration is viable.
3. Update tests and docs.
4. Run `make migrate` if the environment supports it.

## Self-review checklist

Before finalizing:

- Does the diff only contain relevant Latexed changes?
- Are public API contracts preserved or documented?
- Are user content and generated artifacts handled safely?
- Are tests/checks appropriate for changed files?
- Are environment limitations explicit and not hidden?
- Did you avoid introducing stale booking-domain examples?


### CI quality gates

Pull requests should keep the GitHub Actions workflow green across three independent gates:

1. `backend-quality` installs the locked uv environment, runs `make compileall`, `make lint`, `make format-check`, and `make test`.
2. `frontend-static` runs `make frontend-check` without requiring backend dependencies.
3. `docker-build` verifies the backend container image can still be built after the quality gates pass.

When a change touches security-sensitive flows from earlier hardening stages, prefer running `make test-security` locally before the full suite so failures point at the relevant regression area quickly.
