import logging
from datetime import UTC

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import GenerationJob
from app.time_utils import utc_now

logger = logging.getLogger(__name__)


class GenerationJobQueueService:
    """Database-backed queue claiming for persisted generation jobs."""

    def claim_next_job(self, db: Session, *, worker_id: str, owner_id: str | None = None) -> GenerationJob | None:
        query = self._claimable_query(db, owner_id=owner_id)
        candidate = query.order_by(GenerationJob.created_at.asc()).first()
        if candidate is None:
            return None
        return self._claim_candidate(db, candidate=candidate, worker_id=worker_id)

    def claim_job_by_id(
        self, db: Session, *, job_id: str, worker_id: str, owner_id: str | None = None
    ) -> GenerationJob | None:
        candidate = self._claimable_query(db, owner_id=owner_id).filter(GenerationJob.id == job_id).first()
        if candidate is None:
            return None
        return self._claim_candidate(db, candidate=candidate, worker_id=worker_id)

    def _claimable_query(self, db: Session, *, owner_id: str | None = None):
        now = utc_now()
        query = db.query(GenerationJob).filter(
            GenerationJob.status == "queued",
            or_(GenerationJob.next_attempt_at.is_(None), GenerationJob.next_attempt_at <= now),
        )
        if owner_id is not None:
            query = query.filter(GenerationJob.owner_id == owner_id)
        return query

    def _claim_candidate(self, db: Session, *, candidate: GenerationJob, worker_id: str) -> GenerationJob | None:
        now = utc_now()
        updated = (
            db.query(GenerationJob)
            .filter(
                GenerationJob.id == candidate.id,
                GenerationJob.status == "queued",
                or_(GenerationJob.next_attempt_at.is_(None), GenerationJob.next_attempt_at <= now),
            )
            .update(
                {
                    GenerationJob.status: "running",
                    GenerationJob.stage: "generating",
                    GenerationJob.worker_id: worker_id,
                    GenerationJob.locked_at: now,
                    GenerationJob.heartbeat_at: now,
                    GenerationJob.started_at: candidate.started_at or now,
                    GenerationJob.updated_at: now,
                    GenerationJob.attempts: GenerationJob.attempts + 1,
                },
                synchronize_session=False,
            )
        )
        if updated != 1:
            db.rollback()
            return None
        db.commit()
        job = db.query(GenerationJob).filter(GenerationJob.id == candidate.id).one()
        logger.info(
            "generation worker claimed job_id=%s worker_id=%s owner_id=%s attempts=%s",
            job.id,
            worker_id,
            job.owner_id,
            job.attempts,
        )
        return job

    def heartbeat(self, db: Session, *, job_id: str, worker_id: str) -> None:
        now = utc_now()
        updated = (
            db.query(GenerationJob)
            .filter(
                GenerationJob.id == job_id,
                GenerationJob.worker_id == worker_id,
                GenerationJob.status == "running",
            )
            .update(
                {
                    GenerationJob.heartbeat_at: now,
                    GenerationJob.updated_at: now,
                },
                synchronize_session=False,
            )
        )
        if updated:
            db.commit()
            logger.debug("generation worker heartbeat job_id=%s worker_id=%s", job_id, worker_id)
        else:
            db.rollback()

    @staticmethod
    def heartbeat_or_updated_at(job: GenerationJob):
        value = job.heartbeat_at or job.updated_at
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value
