# Latexed release and launch checklist

Use this checklist before a demo, staging deploy, or production release. It is
intentionally split by environment so local degraded workflows do not get
confused with production readiness.

Never paste full AI prompts, lesson transcripts, source materials, generated
LaTeX, API keys, local database files, or uploaded artifacts into release notes,
logs, tickets, or chat. Use request IDs, job IDs, short hashes, endpoint names,
and compact readiness summaries instead.

## Status vocabulary

| Status | Meaning | Can receive user traffic? |
|--------|---------|---------------------------|
| `ready` | Required database/artifact checks pass and optional configured subsystems look usable. | Yes. |
| `degraded` | Core API can serve, but compile, LaTeX packages, transcription, AI provider, worker, or cleanup checks need attention. | Local/demo: often yes. Production: only after explicit operator sign-off for the degraded feature. |
| `not_ready` | Required database or artifact storage is unavailable. | No. Fix before serving traffic. |

`pdflatex` is required for backend PDF compile/export. If it is missing, the
editor, project/file CRUD, templates, local frontend preview, prompt preview,
and many API checks can still be useful, but server-side PDF compile/export are
degraded runtime features rather than frontend bugs.

## Universal pre-flight checks

Run these from the repository root unless noted otherwise.

| Goal | Command or endpoint | Required? | Expected signal |
|------|---------------------|-----------|-----------------|
| Install core locked dependencies | `make sync` | Yes | Completes without installing optional Whisper runtimes. |
| Python syntax | `make compileall` | Yes | No syntax errors. |
| Frontend JavaScript syntax | `make frontend-check` | Yes for frontend/UI changes | `node --check` passes for `frontend/js/*.js`. |
| Backend tests | `make test` | Yes before merge/release | Test suite passes; skips/warnings are reviewed. |
| Full local quality gate | `make check` | Recommended | Compile, frontend syntax, lint, format, and tests pass. |
| Working tree | `git status --short` | Yes before release | Empty except deliberate release artifacts. |
| Runtime URLs | `make open` | Informational | Prints backend/docs/health/frontend URLs. |
| Liveness | `make health` or `GET /api/health` | Yes when backend is running | `status=healthy`. |
| Full readiness | `GET /api/ready` | Yes when backend is running | `ready`, or documented `degraded` reason. |
| Metrics | `GET /api/metrics` | Production/staging | Prometheus text response. |
| Cleanup preview | `make clean-artifacts-dry-run` | Production/staging | JSON report with only trusted roots. |

## Local non-Docker launch checklist

Use this for developer machines and quick demos.

1. Install core dependencies:

   ```bash
   make sync
   ```

2. Start the backend:

   ```bash
   make backend
   ```

3. Start the frontend in another terminal:

   ```bash
   make frontend
   ```

4. Open `http://localhost:8080/main.html`.
5. Check liveness and readiness:

   ```bash
   make health
   curl -fsS http://localhost:8000/api/ready
   ```

6. If PDF compile/export is part of the demo, verify TeX Live and Russian/T2A
   support:

   ```bash
   make latex-check
   ```

7. If `make latex-check` fails, document the demo as degraded for backend
   compile/export. Frontend local preview/export fallback can still be used.
8. If AI generation is part of the demo, verify provider status:

   ```bash
   make ai-provider-status AI_PROVIDER=ollama AI_MODEL=qwen2.5:3b
   ```

9. If queued generation jobs are part of the demo, run a worker:

   ```bash
   make generation-worker
   ```

10. If lesson transcription is part of the demo, install only the needed optional
    runtime and verify status:

    ```bash
    make sync-transcription
    curl -fsS http://localhost:8000/api/transcription/status
    ```

    Use `TRANSCRIPTION_PROVIDER=fake` only for local UI smoke tests. Do not use
    fake transcription as production readiness evidence.

## Docker/staging launch checklist

Use this for staging or production-like Docker validation.

1. Prepare `.env` from reviewed deployment values. Do not use default secrets.
2. Build/start the stack according to the selected compose file:

   ```bash
   cd backend
   docker-compose up --build
   ```

   For production-like compose, validate the rendered configuration first:

   ```bash
   docker compose -f backend/docker-compose.prod.yml config
   ```

3. Run migrations against the target database before serving traffic:

   ```bash
   make migrate
   ```

4. Verify backend health/readiness from the same network path that users or the
   reverse proxy will use:

   ```bash
   curl -fsS http://localhost:8000/api/health
   curl -fsS http://localhost:8000/api/ready
   ```

5. Confirm compile/export runtime:

   ```bash
   make latex-check
   ```

   If compile is sandboxed, also verify the sandbox image and worker host. The
   API container should not need `/var/run/docker.sock`; only the compile worker
   should have Docker runtime access when Docker-based sandbox execution is used.

6. Start required workers separately from the web process:

   ```bash
   make compile-worker
   make generation-worker
   ```

7. Check job pressure and stale jobs:

   ```bash
   curl -fsS http://localhost:8000/api/generation/jobs/operator/status
   ```

8. Verify AI provider status for configured provider/model:

   ```bash
   make ai-provider-status AI_PROVIDER=ollama AI_MODEL=qwen2.5:3b
   ```

9. Run cleanup dry-run and review roots before any destructive cleanup:

   ```bash
   make clean-artifacts-dry-run
   ```

10. Run a browser smoke: open the frontend, create/edit a document, use local
    preview, and either compile through backend or record the compile degraded
    reason from `/api/ready`.

## Production release checklist

Production launch must be stricter than local/staging.

### Required configuration

- `DEPLOYMENT_ENV=production`.
- Non-default `SECRET_KEY`.
- `ALLOWED_HOSTS` does not contain `*`.
- `AUTH_MODE=password` or `AUTH_MODE=trusted_proxy` unless local auth has been
  explicitly approved for a controlled deployment.
- For password auth: `AUTH_REFRESH_TOKEN_PEPPER` is set and `AUTH_COOKIE_SECURE=true`
  when cookie mode is enabled.
- For trusted proxy auth: `TRUSTED_PROXY_IPS` and `TRUSTED_USER_HEADER` are set.
- `AUTO_CREATE_TABLES=false`; run Alembic migrations explicitly.
- `COMPILE_EXECUTION_MODE=sandbox` for untrusted user documents.
- Compile sandbox network is disabled, shell escape is disabled, root filesystem
  is read-only, Linux capabilities are dropped, and no-new-privileges is set.
- Artifact roots are mounted on persistent storage with cleanup policy.
- AI provider credentials/base URLs are set intentionally; keep provider errors
  sanitized unless a non-production debug mode explicitly requires details.

### Required checks

```bash
make sync
make check
make migrate
make latex-check
make clean-artifacts-dry-run
```

With the backend running:

```bash
curl -fsS https://YOUR_HOST/api/health
curl -fsS https://YOUR_HOST/api/ready
curl -fsS https://YOUR_HOST/api/metrics
curl -fsS "https://YOUR_HOST/api/generation/providers/status?provider=YOUR_PROVIDER&model=YOUR_MODEL"
```

### Release gate

Do not serve production traffic if:

- `/api/ready` is `not_ready`.
- Database migrations have not been run against the production database.
- Production still uses default secrets or wildcard hosts.
- Backend compile/export is required by the product launch but `make latex-check`
  fails or `/api/ready` reports missing compiler/packages.
- Required workers are not supervised/restarted separately from the web process.
- Cleanup dry-run reports unexpected roots or paths.

Production may temporarily serve with `degraded` readiness only when the degraded
feature is explicitly out of scope for that launch, documented in release notes,
and visible to operators.

## Post-launch checks

1. Watch `/api/ready` for sustained `degraded` or any `not_ready` status.
2. Watch `/api/metrics` and logs for stale generation jobs, repeated AI `429`,
   provider failures, artifact cleanup errors, and slow requests.
3. Verify workers are alive after deploy/restart.
4. Run `make clean-artifacts-dry-run` on schedule and only run destructive
   cleanup after reviewing the report.
5. Keep incident notes compact: request IDs, job IDs, owner IDs only when needed,
   endpoint/status, provider/model, readiness status, and short hashes.
