from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Artifact
from app.services.artifact_service import (
    ArtifactExpiredError,
    ArtifactMissingFileError,
    ArtifactNotFoundError,
    create_artifact_record,
    get_authorized_artifact_download,
    mark_artifact_accessed,
)
from app.time_utils import utc_now


@pytest.fixture()
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'artifacts.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SessionTesting = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionTesting()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


def test_create_artifact_record_creates_owner_scoped_record(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.settings.UPLOAD_DIR", str(tmp_path / "uploads"))
    source = tmp_path / "source.html"
    source.write_text("<html>ok</html>", encoding="utf-8")

    created = create_artifact_record(
        db_session,
        owner_id="teacher-a",
        project_id="project-1",
        kind="export",
        format="html",
        storage_root="export",
        source_path=source,
        original_filename="Lesson HTML.html",
    )
    db_session.commit()

    artifact = db_session.query(Artifact).filter(Artifact.id == created.id).one()
    assert artifact.owner_id == "teacher-a"
    assert artifact.project_id == "project-1"
    assert artifact.storage_filename.startswith("artifact_")
    assert artifact.storage_filename.endswith(".html")
    assert artifact.original_filename == "Lesson_HTML.html"
    assert created.download_url == f"/api/artifacts/{artifact.id}/download"
    assert not source.exists()


def test_get_authorized_artifact_download_allows_owner_and_rejects_other_owner(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.settings.COMPILE_WORK_DIR", str(tmp_path / "compile"))
    source = tmp_path / "source.pdf"
    source.write_bytes(b"%PDF-1.4 owner")
    created = create_artifact_record(
        db_session,
        owner_id="teacher-a",
        kind="compile_pdf",
        format="pdf",
        storage_root="compile_pdf",
        source_path=source,
        original_filename="main.pdf",
    )
    db_session.commit()

    allowed = get_authorized_artifact_download(db_session, artifact_id=created.id, owner_id="teacher-a")
    assert allowed.target.path.is_file()

    with pytest.raises(ArtifactNotFoundError):
        get_authorized_artifact_download(db_session, artifact_id=created.id, owner_id="teacher-b")


def test_get_authorized_artifact_download_rejects_expired_and_missing_file(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.settings.UPLOAD_DIR", str(tmp_path / "uploads"))
    source = tmp_path / "source.zip"
    source.write_bytes(b"zip")
    created = create_artifact_record(
        db_session,
        owner_id="teacher-a",
        kind="export",
        format="tex_zip",
        storage_root="export",
        source_path=source,
        original_filename="project.zip",
    )
    artifact = db_session.query(Artifact).filter(Artifact.id == created.id).one()
    artifact.expires_at = utc_now() - timedelta(seconds=1)
    db_session.commit()

    with pytest.raises(ArtifactExpiredError):
        get_authorized_artifact_download(db_session, artifact_id=created.id, owner_id="teacher-a")
    db_session.rollback()

    artifact.expires_at = utc_now() + timedelta(hours=1)
    artifact.status = "available"
    db_session.commit()
    download = get_authorized_artifact_download(db_session, artifact_id=created.id, owner_id="teacher-a")
    download.target.path.unlink()

    with pytest.raises(ArtifactMissingFileError):
        get_authorized_artifact_download(db_session, artifact_id=created.id, owner_id="teacher-a")


def test_mark_artifact_accessed_increments_counter(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.settings.UPLOAD_DIR", str(tmp_path / "uploads"))
    source = tmp_path / "source.html"
    source.write_text("ok", encoding="utf-8")
    created = create_artifact_record(
        db_session,
        owner_id="teacher-a",
        kind="export",
        format="html",
        storage_root="export",
        source_path=source,
        original_filename="artifact.html",
    )
    db_session.commit()
    artifact = db_session.query(Artifact).filter(Artifact.id == created.id).one()

    mark_artifact_accessed(db_session, artifact=artifact)

    refreshed = db_session.query(Artifact).filter(Artifact.id == created.id).one()
    assert refreshed.access_count == 1
    assert refreshed.accessed_at is not None
