import uuid

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Project


DEFAULT_TEACHER_ID = "local-teacher"


def _normalize_identity(value: str) -> str:
    identity = value.strip()
    if not identity or len(identity) > 255 or any(ord(char) < 32 for char in identity):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid user identity")
    return identity


def get_current_user_id(request: Request) -> str:
    """Resolve the MVP trusted-proxy identity, falling back to local single-user mode."""
    header_value = request.headers.get(settings.TRUSTED_USER_HEADER)
    return _normalize_identity(header_value or settings.LOCAL_USER_ID or DEFAULT_TEACHER_ID)


def get_project(
    project_id: str,
    db: Session = Depends(get_db),
    owner_id: str = Depends(get_current_user_id),
) -> Project:
    try:
        uuid.UUID(project_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid project ID format"
        )

    project = db.query(Project).filter(Project.id == project_id, Project.owner_id == owner_id).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found"
        )
    return project


def get_project_files(
    project_id: str,
    db: Session = Depends(get_db),
    owner_id: str = Depends(get_current_user_id),
) -> list:
    from app.models import File

    return db.query(File).join(Project).filter(File.project_id == project_id, Project.owner_id == owner_id).all()


def get_current_teacher_id(user_id: str = Depends(get_current_user_id)) -> str:
    """Use the same MVP identity for lesson teacher scoping and project ownership."""
    return user_id
