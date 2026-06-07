# Prompting Guide for Latexed Agents

Use these prompt patterns when asking an AI agent to work on this repository. Good prompts mention Latexed-specific files, behavior, and verification commands.

## Good vs bad prompts

### Bad: vague and stale

```text
Add a booking endpoint and run lint/typecheck.
```

Problems:

- Booking is not this project's domain.
- The repository does not currently define `make lint` or `make typecheck`.
- No files, behavior, or acceptance criteria are named.

### Good: specific Latexed request

```text
Update the AI generation flow so generated LaTeX can be inserted into a new .tex file or replace the current file.

Context:
- Backend generation endpoints are in backend/app/routers/generation.py.
- Frontend AI UI is in frontend/js/07-generation.js.
- Schemas are in backend/app/schemas.py.

Acceptance criteria:
- Preserve provider status and validation behavior.
- Do not log full prompts or raw outputs.
- Run make frontend-check and make test, documenting environment limitations.
```

## Explore prompts

### Broad repository exploration

```text
Explore the Latexed repository and summarize:
- backend routers and their endpoints;
- service modules and responsibilities;
- frontend JS modules and load order;
- existing tests and Makefile checks.
Do not change files.
```

### Feature-specific exploration

```text
Explore how server-side compilation works.
Focus on backend/app/routers/compile.py, backend/app/services/latex_compiler.py,
backend/app/services/latex_sanitizer.py, frontend/js/05-compile-preview.js, and tests.
Identify path-safety and pdflatex environment assumptions.
```

### API/frontend contract exploration

```text
Trace the frontend call path for project files:
frontend startup → API helper → backend file/project routers → schemas/models.
Report the request/response shapes and any compatibility risks.
```

## Plan prompts

### Implementation plan

```text
Create an implementation plan for [feature].
Include:
- files to modify;
- schemas or API contracts affected;
- frontend call sites affected;
- tests/checks to run;
- risks around user LaTeX content, generated PDFs, or AI provider responses.
Do not edit files yet.
```

### Refactor plan

```text
Plan an incremental refactor that moves [behavior] out of a router into a service.
Keep public API behavior unchanged.
List test coverage needed before and after the change.
Avoid broad repository rewrites.
```

## Code prompts

### Backend endpoint/service change

```text
Implement [behavior] for Latexed.
Use backend/app/schemas.py for API contracts and keep non-trivial logic in services.
Do not introduce duplicate schemas.
Add or update backend/tests/test_api.py coverage.
Run make compileall and make test.
```

### Frontend behavior change

```text
Update the frontend [flow] in the appropriate frontend/js module.
Respect script ordering in frontend/main.html and reuse existing helpers like apiRequest and showToast.
Run make frontend-check.
If the change is visually perceptible, run the app and capture a screenshot if possible.
```

### Compile/export safety change

```text
Update compile/export behavior while preserving:
- filename/path sanitization;
- temp directory isolation;
- compile timeout handling;
- no full document logging.
Add tests for pure helpers when possible without requiring pdflatex.
Run make compileall and make test; run make latex-check if relevant.
```

### AI generation change

```text
Update AI generation behavior while preserving:
- provider/model status checks;
- rate and text limits;
- provider error sanitization;
- structural LaTeX validation;
- backend wrapping of model output with the fixed Latexed preamble;
- backend body sanitization, deterministic Safe-mode simplification, safe/rich LaTeX mode rules, environment/math balance validation, compile-check and bounded automatic repair attempts for generated LaTeX when `pdflatex` is available;
- prompt instructions that tell the model to return only document body content, not `\documentclass`, `\usepackage`, `\begin{document}`, or `\end{document}`;
- safe logging with hashes/lengths instead of full prompts.
Update frontend insertion/status UI if response shape changes.
```

## Debugging prompts

### Test failure

```text
Investigate the failing command:
[exact command and output]

Determine whether it is:
- a code regression;
- missing dependency/network issue;
- missing pdflatex/TeX Live environment;
- stale test expectation.
Provide the minimal fix or document the environment limitation.
```

### Production-like bug

```text
Diagnose [bug] in Latexed.
Trace from frontend user action through API request, router, service, and persistence/external boundary.
Do not change files until you identify the likely root cause and propose a focused fix.
```

## Review prompts

### Pre-submission review

```text
Review the current diff for Latexed.
Check:
- API compatibility;
- frontend/backend contract consistency;
- user-content logging risks;
- path traversal or unsafe compiler/provider boundaries;
- missing tests/docs;
- stale booking-domain wording.
```

### Architecture review

```text
Review whether this change follows Latexed architecture boundaries:
Router → Service → Database/session/model or external boundary.
Identify any new router business logic that should move to a service.
Do not request broad refactors unrelated to this change.
```

## Structured prompt template

```markdown
## Context
[Latexed feature, current behavior, relevant files]

## Requested change
[Specific behavior]

## Constraints
- Preserve [API/schema/frontend compatibility].
- Keep logs safe for user LaTeX/prompts.
- Preserve compile/export path safety.
- Do not add stale booking-domain examples.

## Acceptance criteria
- [Behavioral outcome]
- [Tests/docs]
- [Exact checks]

## Non-goals
- [Refactors or features out of scope]

## Expected output
- Summary with file citations
- Testing commands and results
```

## Prompt anti-patterns

- Asking for booking/calendar examples in this repository.
- Asking to run non-existent Makefile targets without first adding them.
- Asking to "just make it work" for compile/export without mentioning path safety.
- Asking to log or paste full prompts/raw LaTeX for debugging.
- Combining broad architecture refactors with unrelated UI changes.
- Ignoring frontend offline fallback behavior.
