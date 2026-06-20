import time

import pytest

from app.database import Base
from test_api import SessionTesting, client, enable_trusted_proxy_auth


@pytest.fixture(autouse=True)
def setup_db():
    from test_api import engine_test

    Base.metadata.drop_all(bind=engine_test)
    Base.metadata.create_all(bind=engine_test)
    yield
    Base.metadata.drop_all(bind=engine_test)


def _payload(topic: str = "Async Job"):
    return {
        "provider": "fake",
        "model": "model",
        "fields": {"topic": topic},
        "materials": "Материал для генерации.",
    }


def test_create_generation_job_returns_202_without_running_orchestrator(monkeypatch):
    from app.routers import generation as generation_router

    async def forbidden_generate(*args, **kwargs):
        raise AssertionError("/api/generation/jobs must not run generation inline")

    monkeypatch.setattr(generation_router.generation_orchestrator, "generate", forbidden_generate)

    started = time.monotonic()
    response = client.post("/api/generation/jobs", json=_payload("No inline"))
    duration = time.monotonic() - started

    assert response.status_code == 202
    assert duration < 2
    data = response.json()
    assert data["status"] == "queued"
    assert data["stage"] == "queued"
    assert data["attempts"] == 0
    assert response.headers["Location"] == f"/api/generation/jobs/{data['id']}"


def test_create_generation_job_idempotency_replay_returns_existing_job(monkeypatch):
    headers = {"Idempotency-Key": "async-job-replay-1"}
    first = client.post("/api/generation/jobs", json=_payload("Replay"), headers=headers)
    second = client.post("/api/generation/jobs", json=_payload("Replay"), headers=headers)

    assert first.status_code == 202
    assert second.status_code == 202
    assert second.json()["id"] == first.json()["id"]
    assert second.headers["Location"] == f"/api/generation/jobs/{first.json()['id']}"


def test_create_generation_job_duplicate_without_idempotency_returns_409():
    payload = _payload("Duplicate active")
    first = client.post("/api/generation/jobs", json=payload)
    second = client.post("/api/generation/jobs", json=payload)

    assert first.status_code == 202
    assert second.status_code == 409
    assert second.headers["Retry-After"].isdigit()


def test_retry_generation_job_requeues_without_running_orchestrator(monkeypatch):
    from app.routers import generation as generation_router
    from app.services.generation_job_worker import generation_job_service

    async def forbidden_generate(*args, **kwargs):
        raise AssertionError("retry must not run generation inline")

    monkeypatch.setattr(generation_router.generation_orchestrator, "generate", forbidden_generate)
    created = client.post("/api/generation/jobs", json=_payload("Retry async"))
    assert created.status_code == 202
    job_id = created.json()["id"]

    db = SessionTesting()
    try:
        job = generation_job_service.get_job(db, job_id=job_id)
        job.status = "failed"
        job.stage = "failed"
        job.error_message = "boom"
        db.add(job)
        db.commit()
    finally:
        db.close()

    retried = client.post(f"/api/generation/jobs/{job_id}/retry")
    assert retried.status_code == 200
    assert retried.json()["status"] == "queued"
    assert retried.headers["Location"] == f"/api/generation/jobs/{job_id}"


def test_generation_job_owner_scoping(monkeypatch):
    enable_trusted_proxy_auth(monkeypatch)
    owner_headers = {"X-Latexed-User": "teacher-a"}
    other_headers = {"X-Latexed-User": "teacher-b"}

    created = client.post("/api/generation/jobs", json=_payload("Scoped async"), headers=owner_headers)
    assert created.status_code == 202
    job_id = created.json()["id"]

    owner_get = client.get(f"/api/generation/jobs/{job_id}", headers=owner_headers)
    other_get = client.get(f"/api/generation/jobs/{job_id}", headers=other_headers)

    assert owner_get.status_code == 200
    assert other_get.status_code == 404
