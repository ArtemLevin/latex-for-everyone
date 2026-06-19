from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import GenerationJob
from app.services.generation_job_queue import GenerationJobQueueService
from app.services.generation_jobs import GenerationJobService
from app.time_utils import utc_now


@pytest.fixture()
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'generation_queue.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SessionTesting = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionTesting()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


def _job(job_id: str, *, status: str = "queued", created_offset: int = 0, next_attempt_offset: int | None = None):
    now = utc_now()
    return GenerationJob(
        id=job_id,
        owner_id="teacher-a",
        provider="fake",
        model="model",
        status=status,
        stage=status,
        request_hash=f"hash-{job_id}",
        request_payload={"provider": "fake", "model": "model", "fields": {}, "materials": "x", "project_id": None},
        attempts=0,
        created_at=now + timedelta(seconds=created_offset),
        updated_at=now + timedelta(seconds=created_offset),
        next_attempt_at=None if next_attempt_offset is None else now + timedelta(seconds=next_attempt_offset),
    )


def test_claim_next_job_claims_oldest_and_sets_lock_fields(db_session):
    db_session.add_all([_job("newer", created_offset=10), _job("older", created_offset=0)])
    db_session.commit()

    claimed = GenerationJobQueueService().claim_next_job(db_session, worker_id="worker-1")

    assert claimed.id == "older"
    assert claimed.status == "running"
    assert claimed.stage == "generating"
    assert claimed.worker_id == "worker-1"
    assert claimed.locked_at is not None
    assert claimed.heartbeat_at is not None
    assert claimed.attempts == 1


def test_claim_next_job_does_not_claim_same_job_twice(db_session):
    db_session.add(_job("job-1"))
    db_session.commit()
    queue = GenerationJobQueueService()

    first = queue.claim_next_job(db_session, worker_id="worker-1")
    second = queue.claim_next_job(db_session, worker_id="worker-2")

    assert first is not None
    assert second is None


def test_claim_next_job_respects_next_attempt_at(db_session):
    db_session.add(_job("future", next_attempt_offset=3600))
    db_session.commit()

    assert GenerationJobQueueService().claim_next_job(db_session, worker_id="worker-1") is None


def test_heartbeat_updates_running_job(db_session):
    db_session.add(_job("job-1"))
    db_session.commit()
    queue = GenerationJobQueueService()
    claimed = queue.claim_next_job(db_session, worker_id="worker-1")
    first_heartbeat = claimed.heartbeat_at

    queue.heartbeat(db_session, job_id=claimed.id, worker_id="worker-1")
    refreshed = db_session.query(GenerationJob).filter(GenerationJob.id == claimed.id).one()

    assert refreshed.heartbeat_at >= first_heartbeat


def test_stale_recovery_uses_heartbeat_at(db_session):
    old = _job("stale", status="running")
    old.worker_id = "worker-1"
    old.heartbeat_at = utc_now() - timedelta(hours=2)
    old.updated_at = utc_now()
    fresh = _job("fresh", status="running")
    fresh.worker_id = "worker-2"
    fresh.heartbeat_at = utc_now()
    db_session.add_all([old, fresh])
    db_session.commit()

    recovered = GenerationJobService().recover_stale_running_jobs(db_session, stale_after_seconds=1800)

    assert [job.id for job in recovered] == ["stale"]
    stale = db_session.query(GenerationJob).filter(GenerationJob.id == "stale").one()
    assert stale.status == "queued"
    assert stale.worker_id is None
    assert stale.heartbeat_at is None
