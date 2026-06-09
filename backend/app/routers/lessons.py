from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_teacher_id
from app.schemas import LessonCreate, LessonResponse, LessonUpdate, MessageResponse
from app.services.lesson_service import LessonNotFoundError, LessonService, PupilNotFoundError

router = APIRouter()
lesson_service = LessonService()


def map_lesson_service_error(exc: Exception) -> HTTPException:
    if isinstance(exc, PupilNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, LessonNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected lesson service error")


@router.get("/", response_model=list[LessonResponse])
async def list_lessons(
    pupil_id: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    teacher_id: str = Depends(get_current_teacher_id),
    db: Session = Depends(get_db),
):
    try:
        return lesson_service.list_lessons(
            db,
            teacher_id,
            pupil_id=pupil_id,
            date_from=date_from,
            date_to=date_to,
            skip=skip,
            limit=limit,
        )
    except PupilNotFoundError as exc:
        raise map_lesson_service_error(exc) from exc


@router.post("/", response_model=LessonResponse, status_code=status.HTTP_201_CREATED)
async def create_lesson(
    lesson_data: LessonCreate,
    teacher_id: str = Depends(get_current_teacher_id),
    db: Session = Depends(get_db),
):
    try:
        return lesson_service.create_lesson(db, teacher_id, lesson_data)
    except PupilNotFoundError as exc:
        raise map_lesson_service_error(exc) from exc


@router.get("/{lesson_id}", response_model=LessonResponse)
async def get_lesson(
    lesson_id: str,
    teacher_id: str = Depends(get_current_teacher_id),
    db: Session = Depends(get_db),
):
    try:
        return lesson_service.get_lesson(db, teacher_id, lesson_id)
    except LessonNotFoundError as exc:
        raise map_lesson_service_error(exc) from exc


@router.patch("/{lesson_id}", response_model=LessonResponse)
async def update_lesson(
    lesson_id: str,
    lesson_data: LessonUpdate,
    teacher_id: str = Depends(get_current_teacher_id),
    db: Session = Depends(get_db),
):
    try:
        return lesson_service.update_lesson(db, teacher_id, lesson_id, lesson_data)
    except LessonNotFoundError as exc:
        raise map_lesson_service_error(exc) from exc


@router.delete("/{lesson_id}", response_model=MessageResponse)
async def delete_lesson(
    lesson_id: str,
    teacher_id: str = Depends(get_current_teacher_id),
    db: Session = Depends(get_db),
):
    try:
        topic = lesson_service.delete_lesson(db, teacher_id, lesson_id)
    except LessonNotFoundError as exc:
        raise map_lesson_service_error(exc) from exc
    return {"message": f"Lesson '{topic}' deleted"}
