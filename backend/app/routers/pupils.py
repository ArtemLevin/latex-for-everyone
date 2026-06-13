from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_teacher_id
from app.schemas import MessageResponse, PupilCreate, PupilResponse, PupilUpdate
from app.services.lesson_service import PupilNotFoundError, PupilService

router = APIRouter()
pupil_service = PupilService()


def map_pupil_service_error(exc: Exception) -> HTTPException:
    if isinstance(exc, PupilNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected pupil service error")


@router.get("/", response_model=list[PupilResponse])
async def list_pupils(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    teacher_id: str = Depends(get_current_teacher_id),
    db: Session = Depends(get_db),
):
    return pupil_service.list_pupils(db, teacher_id, skip=skip, limit=limit)


@router.post("/", response_model=PupilResponse, status_code=status.HTTP_201_CREATED)
async def create_pupil(
    pupil_data: PupilCreate,
    teacher_id: str = Depends(get_current_teacher_id),
    db: Session = Depends(get_db),
):
    return pupil_service.create_pupil(db, teacher_id, pupil_data)


@router.get("/{pupil_id}", response_model=PupilResponse)
async def get_pupil(
    pupil_id: str,
    teacher_id: str = Depends(get_current_teacher_id),
    db: Session = Depends(get_db),
):
    try:
        return pupil_service.get_pupil(db, teacher_id, pupil_id)
    except PupilNotFoundError as exc:
        raise map_pupil_service_error(exc) from exc


@router.patch("/{pupil_id}", response_model=PupilResponse)
async def update_pupil(
    pupil_id: str,
    pupil_data: PupilUpdate,
    teacher_id: str = Depends(get_current_teacher_id),
    db: Session = Depends(get_db),
):
    try:
        return pupil_service.update_pupil(db, teacher_id, pupil_id, pupil_data)
    except PupilNotFoundError as exc:
        raise map_pupil_service_error(exc) from exc


@router.delete("/{pupil_id}", response_model=MessageResponse)
async def delete_pupil(
    pupil_id: str,
    teacher_id: str = Depends(get_current_teacher_id),
    db: Session = Depends(get_db),
):
    try:
        display_name = pupil_service.delete_pupil(db, teacher_id, pupil_id)
    except PupilNotFoundError as exc:
        raise map_pupil_service_error(exc) from exc
    return {"message": f"Pupil '{display_name}' deleted"}
