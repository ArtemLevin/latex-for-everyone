import argparse
import asyncio
import os
import socket
import uuid

from app.config import settings
from app.database import SessionLocal
from app.services.compile_job_worker import CompileJobWorkerService
from app.services.compile_jobs import CompileJobService


def make_worker_id() -> str:
    return settings.COMPILE_WORKER_ID or f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


async def run_once(worker_id: str, *, job_id: str | None = None, recover_stale: bool = False) -> bool:
    db = SessionLocal()
    try:
        job_service = CompileJobService()
        if recover_stale:
            job_service.recover_stale_running_jobs(
                db, stale_after_seconds=settings.COMPILE_JOB_STALE_AFTER_SECONDS, limit=100
            )
        if job_id:
            job = job_service.get_job(db, job_id=job_id)
        else:
            job = job_service.claim_next_job(db, worker_id=worker_id)
        if not job:
            return False
        if job.status == "queued":
            claimed = job_service.claim_next_job(db, worker_id=worker_id)
            if not claimed or claimed.id != job.id:
                return False
            job = claimed
        CompileJobWorkerService(job_service=job_service).run_claimed_job(db, job_id=job.id, worker_id=worker_id)
        return True
    finally:
        db.close()


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run Latexed sandboxed compile jobs.")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--job-id", default=None)
    parser.add_argument("--recover-stale-only", action="store_true")
    args = parser.parse_args()
    worker_id = make_worker_id()
    if args.recover_stale_only:
        db = SessionLocal()
        try:
            CompileJobService().recover_stale_running_jobs(
                db, stale_after_seconds=settings.COMPILE_JOB_STALE_AFTER_SECONDS, limit=100
            )
        finally:
            db.close()
        return
    while True:
        worked = await run_once(worker_id, job_id=args.job_id, recover_stale=True)
        if args.once or args.job_id:
            return
        if not worked:
            await asyncio.sleep(settings.COMPILE_WORKER_IDLE_SLEEP_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
