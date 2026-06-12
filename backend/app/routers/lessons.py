from datetime import datetime

from fastapi import APIRouter, Depends, File as FastAPIFile, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_teacher_id
from app.schemas import (
    LessonAudioRecordingResponse,
    LessonCreate,
    LessonResponse,
    LessonTranscribeRequest,
    LessonTranscriptResponse,
    LessonUpdate,
    MessageResponse,
)
from app.services.audio_storage import (
    AudioPayloadTooLargeError,
    AudioStorageService,
    InvalidAudioFilenameError,
    UnsupportedAudioTypeError,
)
from app.services.lesson_service import LessonNotFoundError, LessonService, PupilNotFoundError
from app.services.transcription import RecordingNotFoundError, TranscriptionService

router = APIRouter()
lesson_service = LessonService()
audio_storage_service = AudioStorageService()
transcription_service = TranscriptionService()


def map_lesson_service_error(exc: Exception) -> HTTPException:
    if isinstance(exc, PupilNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, LessonNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected lesson service error")


def map_transcription_error(exc: Exception) -> HTTPException:
    if isinstance(exc, RecordingNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected transcription error")


def map_audio_storage_error(exc: Exception) -> HTTPException:
    if isinstance(exc, InvalidAudioFilenameError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, UnsupportedAudioTypeError):
        return HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc))
    if isinstance(exc, AudioPayloadTooLargeError):
        return HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc))
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected audio storage error")


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


@router.post(
    "/{lesson_id}/recordings",
    response_model=LessonAudioRecordingResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_lesson_recording(
    lesson_id: str,
    file: UploadFile = FastAPIFile(...),
    teacher_id: str = Depends(get_current_teacher_id),
    db: Session = Depends(get_db),
):
    try:
        lesson = lesson_service.get_lesson(db, teacher_id, lesson_id)
        payload = await file.read(settings.MAX_LESSON_AUDIO_SIZE + 1)
        return audio_storage_service.create_recording(
            db,
            lesson=lesson,
            teacher_id=teacher_id,
            filename=file.filename or "",
            content_type=file.content_type,
            payload=payload,
        )
    except LessonNotFoundError as exc:
        raise map_lesson_service_error(exc) from exc
    except (InvalidAudioFilenameError, UnsupportedAudioTypeError, AudioPayloadTooLargeError) as exc:
        raise map_audio_storage_error(exc) from exc


@router.post(
    "/{lesson_id}/transcribe",
    response_model=LessonTranscriptResponse,
    status_code=status.HTTP_201_CREATED,
)
async def transcribe_lesson(
    lesson_id: str,
    request: LessonTranscribeRequest | None = None,
    teacher_id: str = Depends(get_current_teacher_id),
    db: Session = Depends(get_db),
):
    try:
        lesson = lesson_service.get_lesson(db, teacher_id, lesson_id)
        request_data = request or LessonTranscribeRequest()
        return transcription_service.transcribe_lesson(
            db,
            lesson=lesson,
            recording_id=request_data.recording_id,
            language=request_data.language,
        )
    except LessonNotFoundError as exc:
        raise map_lesson_service_error(exc) from exc
    except RecordingNotFoundError as exc:
        raise map_transcription_error(exc) from exc
