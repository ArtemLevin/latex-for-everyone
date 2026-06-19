from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File as FastAPIFile
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user_id, get_project
from app.models import Project
from app.schemas import FileCreate, FileResponse, FileUpdate, MessageResponse
from app.services.file_service import (
    FileConflictError,
    FileNotFoundError,
    FileService,
    InvalidFileNameError,
)
from app.services.latex_file_policy import LatexFilePolicyError
from app.services.payload_limits import PayloadLimitError
from app.services.upload_limits import (
    UploadDecodeError,
    UploadLimitError,
    read_upload_text_bounded,
    read_uploads_text_bounded,
)

router = APIRouter()
file_service = FileService()


def map_file_service_error(exc: Exception) -> HTTPException:
    if isinstance(exc, FileNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, (InvalidFileNameError, LatexFilePolicyError)):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, FileConflictError):
        detail = str(exc)
        status_code = status.HTTP_400_BAD_REQUEST if "last file" in detail else status.HTTP_409_CONFLICT
        return HTTPException(status_code=status_code, detail=detail)
    if isinstance(exc, (PayloadLimitError, UploadLimitError)):
        return HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc))
    if isinstance(exc, UploadDecodeError):
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected file service error")


@router.get("/project/{project_id}", response_model=list[FileResponse])
async def list_files(
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
):
    return file_service.list_project_files(db, project.id)


@router.post("/project/{project_id}", response_model=FileResponse, status_code=status.HTTP_201_CREATED)
async def create_file(
    file_data: FileCreate,
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
):
    try:
        return file_service.create_file(db, project, file_data)
    except (FileConflictError, InvalidFileNameError, LatexFilePolicyError, PayloadLimitError) as exc:
        raise map_file_service_error(exc) from exc


@router.get("/{file_id}", response_model=FileResponse)
async def get_file(
    file_id: str,
    owner_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    try:
        return file_service.get_file(db, file_id, owner_id=owner_id)
    except FileNotFoundError as exc:
        raise map_file_service_error(exc) from exc


@router.put("/{file_id}", response_model=FileResponse)
async def update_file(
    file_data: FileUpdate,
    file_id: str,
    owner_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    try:
        return file_service.update_file(db, file_id, file_data, owner_id=owner_id)
    except (FileConflictError, FileNotFoundError, InvalidFileNameError, LatexFilePolicyError, PayloadLimitError) as exc:
        raise map_file_service_error(exc) from exc


@router.delete("/{file_id}", response_model=MessageResponse)
async def delete_file(
    file_id: str,
    owner_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    try:
        file_name = file_service.delete_file(db, file_id, owner_id=owner_id)
    except (FileConflictError, FileNotFoundError) as exc:
        raise map_file_service_error(exc) from exc

    return {"message": f"File '{file_name}' deleted"}


@router.post("/{file_id}/upload", response_model=MessageResponse)
async def upload_file(
    file_id: str,
    file: UploadFile = FastAPIFile(...),
    owner_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    try:
        content = await read_upload_text_bounded(
            file,
            max_bytes=settings.MAX_LATEX_UPLOAD_FILE_BYTES,
            chunk_size=settings.UPLOAD_READ_CHUNK_BYTES,
        )
        file_service.replace_file_content(db, file_id, content, owner_id=owner_id)
    except (FileNotFoundError, UploadLimitError, UploadDecodeError, LatexFilePolicyError, PayloadLimitError) as exc:
        raise map_file_service_error(exc) from exc

    return {"message": "File uploaded successfully"}


@router.post("/project/{project_id}/upload-all", response_model=MessageResponse)
async def upload_all_files(
    project: Project = Depends(get_project),
    files: list[UploadFile] = FastAPIFile(...),
    db: Session = Depends(get_db),
):
    try:
        uploads = await read_uploads_text_bounded(
            files,
            max_file_bytes=settings.MAX_LATEX_UPLOAD_FILE_BYTES,
            max_total_bytes=settings.MAX_LATEX_UPLOAD_TOTAL_BYTES,
            max_files=settings.MAX_LATEX_FILES,
            chunk_size=settings.UPLOAD_READ_CHUNK_BYTES,
        )
        uploaded_count = file_service.upload_project_files(db, project, uploads)
    except (InvalidFileNameError, UploadLimitError, UploadDecodeError, LatexFilePolicyError, PayloadLimitError) as exc:
        raise map_file_service_error(exc) from exc

    return {"message": f"Uploaded {uploaded_count} files"}
