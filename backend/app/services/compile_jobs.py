from datetime import timedelta

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import CompileJob
from app.time_utils import utc_now

TERMINAL_COMPILE_JOB_STATUSES = {"completed", "failed", "canceled"}


class CompileJobService:
    def create_job(
        self,
        db: Session,
        *,
        owner_id: str,
        project_id: str | None,
        compile_history_id: str | None,
        main_file_name: str,
        request_payload: dict,
    ) -> CompileJob:
        now = utc_now()
        job = CompileJob(
            owner_id=owner_id,
            project_id=project_id,
            compile_history_id=compile_history_id,
            status="queued",
            stage="queued",
            main_file_name=main_file_name,
            request_payload=request_payload,
            queued_at=now,
            created_at=now,
            updated_at=now,
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        return job

    def get_job(self, db: Session, *, job_id: str, owner_id: str | None = None) -> CompileJob | None:
        query = db.query(CompileJob).filter(CompileJob.id == job_id)
        if owner_id is not None:
            query = query.filter(CompileJob.owner_id == owner_id)
        return query.first()

    def claim_next_job(self, db: Session, *, worker_id: str) -> CompileJob | None:
        now = utc_now()
        job = (
            db.query(CompileJob)
            .filter(CompileJob.status == "queued")
            .order_by(CompileJob.queued_at.asc(), CompileJob.created_at.asc())
            .first()
        )
        if job is None:
            return None
        updated = (
            db.query(CompileJob)
            .filter(CompileJob.id == job.id, CompileJob.status == "queued")
            .update(
                {
                    "status": "running",
                    "stage": "preparing",
                    "worker_id": worker_id,
                    "locked_at": now,
                    "heartbeat_at": now,
                    "started_at": now,
                    "updated_at": now,
                    "attempts": CompileJob.attempts + 1,
                },
                synchronize_session=False,
            )
        )
        if updated != 1:
            db.rollback()
            return None
        db.commit()
        db.refresh(job)
        return job

    def heartbeat(self, db: Session, *, job_id: str, worker_id: str) -> None:
        db.query(CompileJob).filter(CompileJob.id == job_id, CompileJob.worker_id == worker_id).update(
            {"heartbeat_at": utc_now(), "updated_at": utc_now()}, synchronize_session=False
        )
        db.commit()

    def cancel_job(self, db: Session, *, job: CompileJob) -> CompileJob:
        now = utc_now()
        if job.status == "queued":
            job.status = "canceled"
            job.stage = "canceled"
            job.finished_at = now
        elif job.status == "running":
            job.cancel_requested = True
        job.updated_at = now
        db.add(job)
        db.commit()
        db.refresh(job)
        return job

    def mark_completed(
        self, db: Session, *, job: CompileJob, result_payload: dict, pdf_artifact_id: str | None
    ) -> CompileJob:
        now = utc_now()
        job.status = "completed"
        job.stage = "completed"
        job.result_payload = result_payload
        job.error_message = None
        job.pdf_artifact_id = pdf_artifact_id
        job.finished_at = now
        job.updated_at = now
        db.add(job)
        db.commit()
        db.refresh(job)
        return job

    def mark_failed(
        self, db: Session, *, job: CompileJob, error_message: str, result_payload: dict | None = None
    ) -> CompileJob:
        now = utc_now()
        job.status = "failed"
        job.stage = "failed"
        job.error_message = error_message
        job.result_payload = result_payload or {}
        job.finished_at = now
        job.updated_at = now
        db.add(job)
        db.commit()
        db.refresh(job)
        return job

    def recover_stale_running_jobs(self, db: Session, *, stale_after_seconds: int, limit: int = 100) -> int:
        if stale_after_seconds <= 0:
            return 0
        cutoff = utc_now() - timedelta(seconds=stale_after_seconds)
        jobs = (
            db.query(CompileJob)
            .filter(
                CompileJob.status == "running",
                or_(CompileJob.heartbeat_at == None, CompileJob.heartbeat_at < cutoff),  # noqa: E711
            )
            .limit(limit)
            .all()
        )
        for job in jobs:
            job.status = "failed"
            job.stage = "failed"
            job.error_message = "Compile worker heartbeat expired"
            job.finished_at = utc_now()
            job.updated_at = utc_now()
            db.add(job)
        db.commit()
        return len(jobs)
