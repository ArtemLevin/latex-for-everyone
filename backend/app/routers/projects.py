from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime
from app.database import get_db
from app.models import Project, File, ProjectSnapshot
from app.schemas import (
    ProjectCreate, ProjectUpdate, ProjectResponse,
    ProjectDetailResponse, MessageResponse
)
from app.dependencies import get_project
router = APIRouter()


@router.get("/", response_model=list[ProjectResponse])
async def list_projects(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    db: Session = Depends(get_db),
):
    query = db.query(Project)

    if search:
        query = query.filter(Project.name.ilike(f"%{search}%"))

    projects = query.order_by(Project.updated_at.desc()).offset(skip).limit(limit).all()
    return projects


@router.post("/", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    project_data: ProjectCreate,
    db: Session = Depends(get_db),
):
    from app.routers.templates import get_template_content

    project = Project(
        name=project_data.name,
        is_public=project_data.is_public,
    )
    db.add(project)
    db.flush()

    # Create main file
    main_content = ""
    if project_data.template:
        template = get_template_content(project_data.template)
        if template:
            main_content = template["content"]

    main_file = File(
        project_id=project.id,
        name="main.tex",
        content=main_content,
        is_main=True,
    )
    db.add(main_file)
    db.commit()
    db.refresh(project)

    return project


@router.get("/{project_id}", response_model=ProjectDetailResponse)
async def get_project_detail(project: Project = Depends(get_project)):
    return project


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_data: ProjectUpdate,
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
):
    update_data = project_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(project, key, value)

    project.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(project)

    return project


@router.delete("/{project_id}", response_model=MessageResponse)
async def delete_project(
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
):
    db.delete(project)
    db.commit()

    return {"message": f"Project '{project.name}' deleted"}


@router.post("/{project_id}/snapshot", status_code=status.HTTP_201_CREATED)
async def create_snapshot(
    snapshot_data: dict,
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
):
    snapshot = ProjectSnapshot(
        project_id=project.id,
        name=snapshot_data.get("name", "Автосохранение"),
        data=snapshot_data.get("data", {}),
    )
    db.add(snapshot)
    db.commit()

    return {"id": snapshot.id, "created_at": snapshot.created_at}


@router.get("/{project_id}/snapshots")
async def get_snapshots(
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
):
    snapshots = (
        db.query(ProjectSnapshot)
        .filter(ProjectSnapshot.project_id == project.id)
        .order_by(ProjectSnapshot.created_at.desc())
        .limit(50)
        .all()
    )
    return snapshots


@router.post("/{project_id}/restore", response_model=MessageResponse)
async def restore_snapshot(
    snapshot_id: str,
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
):
    snapshot = (
        db.query(ProjectSnapshot)
        .filter(
            ProjectSnapshot.id == snapshot_id,
            ProjectSnapshot.project_id == project.id,
        )
        .first()
    )

    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    # Restore files
    files_data = snapshot.data.get("files", [])

    # Delete existing files
    db.query(File).filter(File.project_id == project.id).delete()

    # Create restored files
    for file_data in files_data:
        file = File(
            project_id=project.id,
            name=file_data["name"],
            content=file_data["content"],
            is_main=file_data.get("is_main", False),
        )
        db.add(file)

    project.updated_at = datetime.utcnow()
    db.commit()

    return {"message": "Snapshot restored successfully"}


@router.post("/{project_id}/duplicate", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def duplicate_project(
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
):
    new_project = Project(
        name=f"{project.name} (копия)",
        is_public=False,
    )
    db.add(new_project)
    db.flush()

    # Copy files
    for file in project.files:
        new_file = File(
            project_id=new_project.id,
            name=file.name,
            content=file.content,
            is_main=file.is_main,
        )
        db.add(new_file)

    db.commit()
    db.refresh(new_project)

    return new_project
