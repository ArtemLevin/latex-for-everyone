from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_project
from app.models import Project
from app.schemas import (
    MessageResponse,
    ProjectCreate,
    ProjectDetailResponse,
    ProjectResponse,
    ProjectUpdate,
    SnapshotCreate,
    SnapshotResponse,
)
from app.services.project_service import (
    ProjectService,
    SnapshotNotFoundError,
    SnapshotProjectMismatchError,
)

router = APIRouter()
project_service = ProjectService()


@router.get("/", response_model=list[ProjectResponse])
async def list_projects(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    db: Session = Depends(get_db),
):
    return project_service.list_projects(db, skip=skip, limit=limit, search=search)


@router.post("/", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    project_data: ProjectCreate,
    db: Session = Depends(get_db),
):
    from app.routers.templates import get_template_content

    return project_service.create_project(db, project_data, template_resolver=get_template_content)


@router.get("/{project_id}", response_model=ProjectDetailResponse)
async def get_project_detail(project: Project = Depends(get_project)):
    return project


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_data: ProjectUpdate,
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
):
    return project_service.update_project(db, project, project_data)


@router.delete("/{project_id}", response_model=MessageResponse)
async def delete_project(
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
):
    project_name = project_service.delete_project(db, project)
    return {"message": f"Project '{project_name}' deleted"}


@router.post("/{project_id}/snapshot", response_model=SnapshotResponse, status_code=status.HTTP_201_CREATED)
async def create_snapshot(
    snapshot_data: SnapshotCreate,
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
):
    try:
        return project_service.create_snapshot(db, project, snapshot_data)
    except SnapshotProjectMismatchError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/{project_id}/snapshots", response_model=list[SnapshotResponse])
async def get_snapshots(
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
):
    return project_service.list_snapshots(db, project)


@router.post("/{project_id}/restore", response_model=MessageResponse)
async def restore_snapshot(
    snapshot_id: str,
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
):
    try:
        project_service.restore_snapshot(db, project, snapshot_id)
    except SnapshotNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return {"message": "Snapshot restored successfully"}


@router.post("/{project_id}/duplicate", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def duplicate_project(
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
):
    return project_service.duplicate_project(db, project)
