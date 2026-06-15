# Latexed operations runbook

This runbook is for local operators and production maintainers of Latexed. It
focuses on observable symptoms, likely causes and safe actions. Do not paste full
AI prompts, lesson transcripts, source materials, API keys or generated LaTeX into
logs, tickets or chat messages; use request IDs, job IDs, short hashes and status
summaries instead.

## First checks

| Goal | Command or endpoint | Expected signal |
|------|---------------------|-----------------|
| Backend process responds | `GET /api/health` or `make health` | `status=healthy` |
| Full readiness summary | `GET /api/ready` | `ready`, `degraded` or `not_ready`; includes `ai_request_control` details |
| AI provider status | `GET /api/generation/providers/status?provider=...&model=...` | Provider/model availability without generation |
| Generation job pressure | `GET /api/generation/jobs/operator/status` | Owner-scoped counts, backlog and stale samples |
| Transcription runtime | `GET /api/transcription/status` | Provider, missing requirements and install hint |
| Artifact cleanup preview | `make clean-artifacts-dry-run` | JSON report without deleting files |

## Status interpretation

| Status | Meaning | Operator action |
|--------|---------|-----------------|
| `ready` | Required DB/artifact checks pass and optional subsystems look usable. | Normal operation. |
| `degraded` | Core API can serve, but compile, LaTeX packages, transcription or generation-worker checks need attention. | Check the failing section in `/api/ready` and the symptom tables below. |
| `not_ready` | Required DB or artifact directories are unavailable. | Do not send user traffic until DB/artifact storage is fixed. |

## AI generation and job workers

| Symptom | Likely cause | Safe action |
|---------|--------------|-------------|
| `429 Too Many Requests` from `/api/generation/*` | Per-client AI rate limit was exceeded. | Wait for `Retry-After`; do not add frontend auto-retry loops. If this happens during normal use, review duplicate submits, `AI_RATE_LIMIT_PER_MINUTE`, and whether `AI_REQUEST_CONTROL_BACKEND=redis` is needed for multi-replica deployments. |
| `409` duplicate generation submit | Same in-flight request fingerprint is already running. | Wait for current job/poll result; use idempotency keys for safe client retries. |
| Job stays `queued` | `AI_GENERATION_JOB_EXECUTION_MODE=external` but worker is not running, or worker cannot reach DB/provider. | Start `make generation-worker` or inspect worker process logs. Use `GET /api/generation/jobs/operator/status` for backlog. |
| Job stays `running` longer than expected | Provider call is slow, worker was interrupted, or stale recovery threshold is disabled/too high. | Check `run_duration_seconds`, worker logs and `/api/ready` `generation_jobs.stale_running`. If stale, run recovery below. |
| `/api/ready` is `degraded` with `generation_jobs` error | Stale running generation jobs were detected. | Run `make generation-worker-recover-stale` or call `POST /api/generation/jobs/operator/recover-stale` for the current owner. |
| `/api/ready` is `degraded` with `ai_request_control` error | Redis request-control backend is misconfigured or unreachable. | Check `AI_REQUEST_CONTROL_BACKEND`, `AI_REQUEST_CONTROL_REDIS_URL`, Redis network access and credentials; fall back to `memory` only for single-replica deployments. |
| Job `failed` with provider error | Ollama/vendor provider unavailable, timeout, bad model or invalid upstream response. | Check `/api/generation/providers/status`, provider service logs and model configuration. Keep `AI_EXPOSE_PROVIDER_ERRORS=false` in production. |

### Generation worker commands

```bash
make generation-worker
make generation-worker-once
make generation-worker-recover-stale
PYTHONPATH=backend python backend/scripts/run_generation_jobs.py --once --job-id <job-id>
PYTHONPATH=backend python backend/scripts/run_generation_jobs.py --recover-stale-only --stale-after-seconds 600
```

Recommended starting points:

- local Ollama small models: `AI_GENERATION_JOB_STALE_AFTER_SECONDS=900`;
- larger local models: `AI_GENERATION_JOB_STALE_AFTER_SECONDS=1800` or higher;
- vendor APIs with strict timeouts: align stale threshold with provider timeout plus deployment grace period.

## LaTeX compile/export

| Symptom | Likely cause | Safe action |
|---------|--------------|-------------|
| `/api/ready` compiler check is `missing` | `pdflatex` is not on `PATH`. | Install TeX Live or set `LATEX_COMPILER`; run `make latex-check`. |
| LaTeX package readiness is `missing` | Russian babel/T2A support is missing. | Install Cyrillic/Russian TeX packages such as `texlive-lang-cyrillic`; rerun `make latex-check`. |
| Compile API returns timeout or truncated logs | Document is too slow/noisy for configured limits. | Inspect bounded compile log, simplify document, or tune `COMPILE_TIMEOUT`/`MAX_COMPILER_OUTPUT_CHARS`. |
| Export/download cannot find artifact | Artifact expired, cleanup ran, or path is outside trusted roots. | Recompile/export; never bypass trusted artifact resolver with raw paths. |

## Transcription and lesson documents

| Symptom | Likely cause | Safe action |
|---------|--------------|-------------|
| Transcript is persisted as `failed` with disabled-provider message | `TRANSCRIPTION_PROVIDER=disabled`. | Install/configure a provider or use `TRANSCRIPTION_PROVIDER=fake` only for local smoke tests. |
| `/api/transcription/status` reports missing `faster_whisper` | Optional Python runtime is not installed. | Run `uv sync --group transcription` or install the documented pinned package. |
| Missing `ffmpeg`/`ffprobe` in transcription status | System media tools are absent. | Install ffmpeg package in host/container image and rerun readiness. |
| Lesson document generation creates `draft` | Transcript was not reviewed and request explicitly allowed unreviewed text. | Review/edit transcript and regenerate final documents when appropriate. |

## Artifact cleanup

| Symptom | Likely cause | Safe action |
|---------|--------------|-------------|
| Runtime artifact volume grows | Cleanup is not scheduled or TTL is too high. | Run `make clean-artifacts-dry-run`; if report is safe, schedule `make clean-artifacts`. |
| Cleanup skips paths | Path is outside trusted root, is fresh, or violates cleanup policy. | Treat skips as safety signals; update trusted roots deliberately, not by wildcard deletion. |
| Cleanup errors | Permission issue or missing directory parent. | Fix filesystem ownership/volume mounts; rerun dry-run first. |

## Logging checklist

Include these fields in incident notes when available:

- `X-Request-ID` / `request_id`;
- generation `job_id`;
- `owner_id` only when needed for scoped debugging;
- endpoint path and HTTP status;
- provider/model names;
- readiness check status and compact details.

Do not include full prompts, full source materials, full transcripts, generated documents, API keys or local database files.

## Deployment notes

For external workers, run the web process and worker process separately. In
systemd or Docker, configure process supervision to restart failed workers and
alert on `/api/ready` degraded generation-job checks. A minimal deployment has:

1. web process: FastAPI backend;
2. frontend static server or same-origin static hosting;
3. one or more `generation-worker` processes when `AI_GENERATION_JOB_EXECUTION_MODE=external`;
4. scheduled `clean-artifacts-dry-run` reporting and a deliberate cleanup schedule;
5. readiness probes that alert on `not_ready` immediately and on sustained `degraded` status.

## Alert thresholds

Use the thresholds below as starting points and tune them after observing real
traffic. They intentionally avoid inspecting user prompt or transcript content.

| Signal | Suggested threshold | Severity | First response |
|--------|---------------------|----------|----------------|
| `GET /api/ready` returns `not_ready` | Any single production probe | Page | Check DB connectivity and artifact roots before serving traffic. |
| `GET /api/ready` returns sustained `degraded` | 5 minutes | Warning | Inspect degraded sections; prioritize compiler and `generation_jobs`. |
| `generation_jobs.stale_running > 0` | More than one probe window | Warning | Run stale recovery and inspect worker/provider logs. |
| Generation queued backlog | More than 10 queued jobs for 10 minutes in small deployments | Warning | Start or scale workers; check provider throughput and DB latency. |
| Repeated AI `429` responses | Burst above normal baseline for 5 minutes | Warning | Confirm frontend is not retrying automatically and review rate-limit settings. |
| Cleanup dry-run would delete unexpected roots | Any unexpected path | Page before commit cleanup | Stop cleanup and verify trusted-root configuration. |

## Deployment examples

### systemd generation worker

```ini
[Unit]
Description=Latexed generation worker
After=network.target

[Service]
WorkingDirectory=/srv/latexed
Environment=PYTHONPATH=/srv/latexed/backend
Environment=AI_GENERATION_JOB_EXECUTION_MODE=external
ExecStart=/srv/latexed/.venv/bin/python backend/scripts/run_generation_jobs.py --recover-stale --stale-after-seconds 900
Restart=always
RestartSec=5
User=latexed
Group=latexed

[Install]
WantedBy=multi-user.target
```

### Docker Compose generation worker

```yaml
services:
  generation-worker:
    image: latexed-backend:latest
    command: >
      python backend/scripts/run_generation_jobs.py
      --recover-stale
      --stale-after-seconds 900
    environment:
      AI_GENERATION_JOB_EXECUTION_MODE: external
      DATABASE_URL: ${DATABASE_URL}
      OLLAMA_BASE_URL: ${OLLAMA_BASE_URL:-http://ollama:11434}
    volumes:
      - latexed-artifacts:/app/backend/artifacts
    restart: unless-stopped
```

Run only one worker at first for local SQLite deployments. Scale workers after
moving to a production database that can handle concurrent job claims.

## Runbook snippets

### Recover stale generation jobs

1. Confirm stale jobs with `GET /api/generation/jobs/operator/status`.
2. Run `make generation-worker-recover-stale` or call
   `POST /api/generation/jobs/operator/recover-stale` with a reviewed threshold.
3. Start `make generation-worker` and verify queued/running counts decrease.

### Clean artifacts safely

1. Run `make clean-artifacts-dry-run` and archive the JSON report.
2. Confirm all candidate paths are under expected compile/export/lesson roots.
3. Run `make clean-artifacts` only after the dry-run report is reviewed.

### Verify LaTeX runtime

1. Run `make latex-check` on the same host/container image that serves compile.
2. If Russian package checks fail, install Cyrillic language packages.
3. Recheck `/api/ready` before enabling user traffic.

### Verify transcription runtime

1. Call `GET /api/transcription/status`.
2. If dependencies are missing, install `uv sync --group transcription` and
   system `ffmpeg`/`ffprobe` packages in the runtime image.
3. Set `TRANSCRIPTION_PROVIDER` deliberately; use `fake` only for local smoke
   testing and `disabled` when transcription is intentionally unavailable.

## Known next gaps

- Redis-backed AI request control shares rate-limit and duplicate-guard state, but still needs production load testing and dashboards before broad horizontal scaling.
- Generation jobs are durable in the database, but this is not yet a full queue
  system with priorities and dead-letter routing.
- Metrics are exposed through JSON readiness/operator endpoints rather than a
  Prometheus exporter; add an exporter before relying on dashboard-only alerts.
