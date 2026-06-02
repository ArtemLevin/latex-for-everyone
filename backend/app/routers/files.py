from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File as FastAPIFile
from sqlalchemy.orm import Session
from datetime import datetime
from app.database import get_db
from app.models import File, Project
from app.schemas import FileCreate, FileUpdate, FileResponse, MessageResponse
from app.dependencies import get_project, get_project_files
import os

router = APIRouter()


@router.get("/project/{project_id}", response_model=list[FileResponse])
async def list_files(
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
):
    files = (
        db.query(File)
        .filter(File.project_id == project.id)
        .order_by(File.is_main.desc(), File.name)
        .all()
    )
    return files


@router.post("/project/{project_id}", response_model=FileResponse, status_code=status.HTTP_201_CREATED)
async def create_file(
    file_data: FileCreate,
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
):
    # Check for duplicate name
    existing = (
        db.query(File)
        .filter(File.project_id == project.id, File.name == file_data.name)
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"File '{file_data.name}' already exists"
        )

    # If setting as main, unset other main files
    if file_data.is_main:
        db.query(File).filter(
            File.project_id == project.id,
            File.is_main == True,
        ).update({"is_main": False})

    new_file = File(
        project_id=project.id,
        name=file_data.name,
        content=file_data.content,
        is_main=file_data.is_main,
    )
    db.add(new_file)
    db.commit()
    db.refresh(new_file)

    return new_file


@router.get("/{file_id}", response_model=FileResponse)
async def get_file(
    file_id: str,
    db: Session = Depends(get_db),
):
    file = db.query(File).filter(File.id == file_id).first()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    return file


@router.put("/{file_id}", response_model=FileResponse)
async def update_file(
    file_data: FileUpdate,
    file_id: str,
    db: Session = Depends(get_db),
):
    file = db.query(File).filter(File.id == file_id).first()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")

    update_data = file_data.model_dump(exclude_unset=True)

    # Check name conflict
    if "name" in update_data:
        existing = (
            db.query(File)
            .filter(
                File.project_id == file.project_id,
                File.name == update_data["name"],
                File.id != file_id,
            )
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"File '{update_data['name']}' already exists"
            )

    # If setting as main, unset others
    if update_data.get("is_main"):
        db.query(File).filter(
            File.project_id == file.project_id,
            File.is_main == True,
            File.id != file_id,
        ).update({"is_main": False})

    for key, value in update_data.items():
        setattr(file, key, value)

    file.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(file)

    return file


@router.delete("/{file_id}", response_model=MessageResponse)
async def delete_file(
    file_id: str,
    db: Session = Depends(get_db),
):
    file = db.query(File).filter(File.id == file_id).first()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")

    project = db.query(Project).filter(Project.id == file.project_id).first()

    # Don't delete last file
    file_count = db.query(File).filter(File.project_id == file.project_id).count()
    if file_count <= 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete the last file in project"
        )

    db.delete(file)
    db.commit()

    return {"message": f"File '{file.name}' deleted"}


@router.post("/{file_id}/upload", response_model=MessageResponse)
async def upload_file(
    file_id: str,
    file: UploadFile = FastAPIFile(...),
    db: Session = Depends(get_db),
):
    db_file = db.query(File).filter(File.id == file_id).first()
    if not db_file:
        raise HTTPException(status_code=404, detail="File not found")

    content = await file.read()
    db_file.content = content.decode("utf-8")
    db_file.updated_at = datetime.utcnow()
    db.commit()

    return {"message": "File uploaded successfully"}


@router.post("/project/{project_id}/upload-all", response_model=MessageResponse)
async def upload_all_files(
    project_id: str,
    files: list[UploadFile] = FastAPIFile(...),
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    for upload_file in files:
        content = await upload_file.read()
        name = upload_file.filename

        # Check if file exists
        existing = (
            db.query(File)
            .filter(File.project_id == project_id, File.name == name)
            .first()
        )

        if existing:
            existing.content = content.decode("utf-8")
            existing.updated_at = datetime.utcnow()
        else:
            new_file = File(
                project_id=project_id,
                name=name,
                content=content.decode("utf-8"),
            )
            db.add(new_file)

    db.commit()

    return {"message": f"Uploaded {len(files)} files"}
