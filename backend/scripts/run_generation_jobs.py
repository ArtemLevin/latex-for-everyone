#!/usr/bin/env python3
"""Compatibility wrapper for running queued Latexed AI generation jobs.

The canonical entrypoint is ``python -m app.workers.generation_worker``. The
``/api/generation/jobs`` API always persists queued jobs without running
provider calls in the web process; this script remains for existing runbooks.
"""
import argparse
import asyncio
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.config import settings  # noqa: E402
from app.services.generation_job_worker import (  # noqa: E402
    recover_stale_generation_jobs,
    run_generation_job_once,
    run_generation_worker_loop,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run queued Latexed AI generation jobs.")
    parser.add_argument("--job-id", default=None, help="Run one specific queued generation job id.")
    parser.add_argument("--owner-id", default=None, help="Restrict queued job claims to one owner id.")
    parser.add_argument("--once", action="store_true", help="Run at most one queued job and exit.")
    parser.add_argument("--max-jobs", type=int, default=0, help="Stop after processing N jobs; 0 means run forever.")
    parser.add_argument("--poll-interval-seconds", type=float, default=2.0, help="Idle sleep interval for the worker loop.")
    parser.add_argument(
        "--stale-after-seconds",
        type=int,
        default=settings.AI_GENERATION_JOB_STALE_AFTER_SECONDS,
        help="Recover running jobs with heartbeat older than this threshold; 0 disables recovery.",
    )
    parser.add_argument("--recover-stale", action="store_true", help="Recover stale running jobs before processing queued work.")
    parser.add_argument("--recover-stale-only", action="store_true", help="Recover stale running jobs and exit without processing work.")
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=settings.AI_GENERATION_JOB_TIMEOUT_SECONDS,
        help="Per-job timeout; 0 uses no persisted timeout failure.",
    )
    args = parser.parse_args()

    if args.recover_stale or args.recover_stale_only:
        recover_stale_generation_jobs(owner_id=args.owner_id, stale_after_seconds=args.stale_after_seconds)
        if args.recover_stale_only:
            return 0

    if args.once or args.job_id:
        job = asyncio.run(
            run_generation_job_once(
                job_id=args.job_id,
                owner_id=args.owner_id,
                timeout_seconds=args.timeout_seconds,
            )
        )
        return 0

    asyncio.run(
        run_generation_worker_loop(
            poll_interval_seconds=args.poll_interval_seconds,
            max_jobs=args.max_jobs,
            owner_id=args.owner_id,
            timeout_seconds=args.timeout_seconds,
            stale_after_seconds=args.stale_after_seconds,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
