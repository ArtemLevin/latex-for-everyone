# Sandboxed LaTeX compilation

Latexed supports a persisted compile-job flow so production deployments can keep
untrusted LaTeX out of the API process:

1. `POST /api/compile/jobs` validates project ownership and payload limits, creates
   `CompileHistory`, persists a queued `CompileJob`, and returns `202 Accepted`
   with `Location: /api/compile/jobs/{job_id}`.
2. `python -m app.workers.compile_worker` claims queued jobs from the database.
3. The worker runs each job through the configured compile runner and publishes a
   successful PDF through the owner-scoped artifact service.

## Runtime modes

- `COMPILE_EXECUTION_MODE=local_subprocess` is for development and CI without a
  container runtime. It still passes `-no-shell-escape` and TeX `openin_any` /
  `openout_any` policy, but it is not a sandbox.
- `COMPILE_EXECUTION_MODE=sandbox` runs a one-shot Docker container with no
  network, non-root UID/GID, read-only root filesystem, memory/CPU/PID limits,
  `cap_drop=ALL`, `no-new-privileges`, Docker default seccomp, and explicit
  `pdflatex -no-shell-escape`.

Production startup fails unless `COMPILE_EXECUTION_MODE=sandbox` and the key
sandbox hardening flags remain enabled.

## Build and run

```bash
docker build -f docker/latex-sandbox/Dockerfile -t latexed-latex-sandbox:latest .
make compile-worker
```

The compile worker may need container-runtime access in development. Mounting
`/var/run/docker.sock` is powerful: do not mount it into the API container. For
production, prefer rootless Docker, an isolated compile host, or a remote sandbox
service so only the worker can start one-shot compile containers.
