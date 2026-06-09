import uuid

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Project


def get_project(project_id: str, db: Session = Depends(get_db)) -> Project:
    try:
        uuid.UUID(project_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid project ID format"
        )

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found"
        )
    return project


def get_project_files(project_id: str, db: Session = Depends(get_db)) -> list:
    from app.models import File
    return db.query(File).filter(File.project_id == project_id).all()


DEFAULT_TEACHER_ID = "local-teacher"


def get_current_teacher_id() -> str:
    """Placeholder teacher scope until full auth/ownership is implemented."""
    return DEFAULT_TEACHER_ID
