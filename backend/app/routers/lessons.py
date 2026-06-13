from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, File as FastAPIFile, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_teacher_id
from app.schemas import (
    LessonAudioRecordingResponse,
    LessonCreate,
    LessonDocumentGenerateRequest,
    LessonGeneratedDocumentResponse,
    LessonProcessingJobCreate,
    LessonProcessingJobResponse,
    LessonResponse,
    LessonTranscribeRequest,
    LessonTranscriptResponse,
    LessonTranscriptUpdate,
    LessonUpdate,
    MessageResponse,
)
from app.services.audio_storage import (
    AudioDurationTooLongError,
    AudioPayloadTooLargeError,
    AudioStorageService,
    InvalidAudioFilenameError,
    UnsupportedAudioTypeError,
)
from app.services.lesson_documents import (
    LessonDocumentGenerationService,
    LessonDocumentNotFoundError,
    LessonDocumentProviderError,
    LessonPromptError,
    LessonTranscriptNotFoundError,
)
from app.services.lesson_jobs import (
    LessonJobConflictError,
    LessonJobNotFoundError,
    LessonProcessingJobService,
    run_lesson_processing_job_once,
)
from app.services.lesson_service import LessonNotFoundError, LessonService, PupilNotFoundError
from app.services.transcription import (
    LessonTranscriptNotFoundError as TranscriptionTranscriptNotFoundError,
    LessonTranscriptReviewError,
    LessonTranscriptService,
    RecordingNotFoundError,
    TranscriptionService,
)

router = APIRouter()
lesson_service = LessonService()
audio_storage_service = AudioStorageService()
transcription_service = TranscriptionService()
lesson_transcript_service = LessonTranscriptService()
lesson_document_service = LessonDocumentGenerationService()
lesson_job_service = LessonProcessingJobService(
    transcription_service=transcription_service,
    document_service=lesson_document_service,
)


def map_lesson_service_error(exc: Exception) -> HTTPException:
    if isinstance(exc, PupilNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, LessonNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected lesson service error")


def map_transcription_error(exc: Exception) -> HTTPException:
    if isinstance(exc, (RecordingNotFoundError, TranscriptionTranscriptNotFoundError)):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, LessonTranscriptReviewError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected transcription error")


def map_lesson_document_error(exc: Exception) -> HTTPException:
    if isinstance(exc, (LessonTranscriptNotFoundError, LessonDocumentNotFoundError)):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, LessonPromptError):
        return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Lesson prompt template is not available")
    if isinstance(exc, LessonDocumentProviderError):
        return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected lesson document error")


def map_lesson_job_error(exc: Exception) -> HTTPException:
    if isinstance(exc, LessonJobNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, LessonJobConflictError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected lesson processing job error")


def map_audio_storage_error(exc: Exception) -> HTTPException:
    if isinstance(exc, InvalidAudioFilenameError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, UnsupportedAudioTypeError):
        return HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc))
    if isinstance(exc, (AudioPayloadTooLargeError, AudioDurationTooLongError)):
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
    except (InvalidAudioFilenameError, UnsupportedAudioTypeError, AudioPayloadTooLargeError, AudioDurationTooLongError) as exc:
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


@router.get(
    "/{lesson_id}/transcripts",
    response_model=list[LessonTranscriptResponse],
)
async def list_lesson_transcripts(
    lesson_id: str,
    teacher_id: str = Depends(get_current_teacher_id),
    db: Session = Depends(get_db),
):
    try:
        lesson = lesson_service.get_lesson(db, teacher_id, lesson_id)
        return lesson_transcript_service.list_transcripts(db, lesson=lesson)
    except LessonNotFoundError as exc:
        raise map_lesson_service_error(exc) from exc


@router.get(
    "/{lesson_id}/transcripts/{transcript_id}",
    response_model=LessonTranscriptResponse,
)
async def get_lesson_transcript(
    lesson_id: str,
    transcript_id: str,
    teacher_id: str = Depends(get_current_teacher_id),
    db: Session = Depends(get_db),
):
    try:
        lesson = lesson_service.get_lesson(db, teacher_id, lesson_id)
        return lesson_transcript_service.get_transcript(db, lesson=lesson, transcript_id=transcript_id)
    except LessonNotFoundError as exc:
        raise map_lesson_service_error(exc) from exc
    except TranscriptionTranscriptNotFoundError as exc:
        raise map_transcription_error(exc) from exc


@router.patch(
    "/{lesson_id}/transcripts/{transcript_id}",
    response_model=LessonTranscriptResponse,
)
async def update_lesson_transcript_review(
    lesson_id: str,
    transcript_id: str,
    request: LessonTranscriptUpdate,
    teacher_id: str = Depends(get_current_teacher_id),
    db: Session = Depends(get_db),
):
    try:
        lesson = lesson_service.get_lesson(db, teacher_id, lesson_id)
        return lesson_transcript_service.update_transcript_review(
            db,
            lesson=lesson,
            transcript_id=transcript_id,
            edited_text=request.edited_text,
            review_status=request.review_status,
        )
    except LessonNotFoundError as exc:
        raise map_lesson_service_error(exc) from exc
    except (TranscriptionTranscriptNotFoundError, LessonTranscriptReviewError) as exc:
        raise map_transcription_error(exc) from exc


def document_response(document) -> LessonGeneratedDocumentResponse:
    response = LessonGeneratedDocumentResponse.model_validate(document)
    response.download_url = f"/api/lessons/{document.lesson_id}/documents/{document.id}/download"
    return response


@router.post(
    "/{lesson_id}/documents/generate",
    response_model=list[LessonGeneratedDocumentResponse],
    status_code=status.HTTP_201_CREATED,
)
async def generate_lesson_documents(
    lesson_id: str,
    request: LessonDocumentGenerateRequest | None = None,
    teacher_id: str = Depends(get_current_teacher_id),
    db: Session = Depends(get_db),
):
    try:
        lesson = lesson_service.get_lesson(db, teacher_id, lesson_id)
        request_data = request or LessonDocumentGenerateRequest()
        documents = await lesson_document_service.generate_documents(
            db,
            lesson=lesson,
            document_types=request_data.document_types or None,
            transcript_id=request_data.transcript_id,
        )
        return [document_response(document) for document in documents]
    except LessonNotFoundError as exc:
        raise map_lesson_service_error(exc) from exc
    except (LessonTranscriptNotFoundError, LessonPromptError, LessonDocumentProviderError) as exc:
        raise map_lesson_document_error(exc) from exc


@router.get("/{lesson_id}/documents", response_model=list[LessonGeneratedDocumentResponse])
async def list_lesson_documents(
    lesson_id: str,
    teacher_id: str = Depends(get_current_teacher_id),
    db: Session = Depends(get_db),
):
    try:
        lesson = lesson_service.get_lesson(db, teacher_id, lesson_id)
        documents = lesson_document_service.list_documents(db, lesson=lesson)
        return [document_response(document) for document in documents]
    except LessonNotFoundError as exc:
        raise map_lesson_service_error(exc) from exc


@router.get("/{lesson_id}/documents/{document_id}/download")
async def download_lesson_document(
    lesson_id: str,
    document_id: str,
    teacher_id: str = Depends(get_current_teacher_id),
    db: Session = Depends(get_db),
):
    try:
        lesson = lesson_service.get_lesson(db, teacher_id, lesson_id)
        document = lesson_document_service.get_document(db, lesson=lesson, document_id=document_id)
        path = lesson_document_service.resolve_document_path(document)
        if not path.is_file():
            raise LessonDocumentNotFoundError("Lesson document artifact not found")
        return FileResponse(path, media_type=document.content_type, filename=document.filename)
    except LessonNotFoundError as exc:
        raise map_lesson_service_error(exc) from exc
    except LessonDocumentNotFoundError as exc:
        raise map_lesson_document_error(exc) from exc


@router.post(
    "/{lesson_id}/processing-jobs",
    response_model=LessonProcessingJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_lesson_processing_job(
    lesson_id: str,
    background_tasks: BackgroundTasks,
    request: LessonProcessingJobCreate | None = None,
    teacher_id: str = Depends(get_current_teacher_id),
    db: Session = Depends(get_db),
):
    try:
        lesson = lesson_service.get_lesson(db, teacher_id, lesson_id)
        request_data = request or LessonProcessingJobCreate()
        if settings.LESSON_JOB_EXECUTION_MODE.strip().lower() == "background":
            job = lesson_job_service.create_job(db, lesson=lesson, request=request_data)
            background_tasks.add_task(run_lesson_processing_job_once, job.id)
            return job
        return await lesson_job_service.create_and_run_job(db, lesson=lesson, request=request_data)
    except LessonNotFoundError as exc:
        raise map_lesson_service_error(exc) from exc
    except LessonJobConflictError as exc:
        raise map_lesson_job_error(exc) from exc


@router.get("/{lesson_id}/processing-jobs", response_model=list[LessonProcessingJobResponse])
async def list_lesson_processing_jobs(
    lesson_id: str,
    teacher_id: str = Depends(get_current_teacher_id),
    db: Session = Depends(get_db),
):
    try:
        lesson = lesson_service.get_lesson(db, teacher_id, lesson_id)
        return lesson_job_service.list_jobs(db, lesson=lesson)
    except LessonNotFoundError as exc:
        raise map_lesson_service_error(exc) from exc


@router.get("/{lesson_id}/processing-jobs/{job_id}", response_model=LessonProcessingJobResponse)
async def get_lesson_processing_job(
    lesson_id: str,
    job_id: str,
    teacher_id: str = Depends(get_current_teacher_id),
    db: Session = Depends(get_db),
):
    try:
        lesson = lesson_service.get_lesson(db, teacher_id, lesson_id)
        return lesson_job_service.get_job(db, lesson=lesson, job_id=job_id)
    except LessonNotFoundError as exc:
        raise map_lesson_service_error(exc) from exc
    except LessonJobNotFoundError as exc:
        raise map_lesson_job_error(exc) from exc
