from datetime import datetime
from typing import Optional, Any, Literal
from pydantic import BaseModel, ConfigDict, Field


# File Schemas
class FileBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    content: str = ""
    is_main: bool = False


class FileCreate(FileBase):
    pass


class FileUpdate(BaseModel):
    name: Optional[str] = None
    content: Optional[str] = None
    is_main: Optional[bool] = None


class FileResponse(FileBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    created_at: datetime
    updated_at: datetime


# Project Schemas
class ProjectBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    is_public: bool = False


class ProjectCreate(ProjectBase):
    template: Optional[str] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    is_public: Optional[bool] = None
    settings: Optional[dict[str, Any]] = None


class ProjectResponse(ProjectBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    owner_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    settings: dict[str, Any] = Field(default_factory=dict)


class ProjectDetailResponse(ProjectResponse):
    files: list[FileResponse] = Field(default_factory=list)


# Lesson/Pupil Schemas
class PupilCreate(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=255)
    notes: Optional[str] = None


class PupilUpdate(BaseModel):
    display_name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    notes: Optional[str] = None


class PupilResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    teacher_id: str
    display_name: str
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class LessonCreate(BaseModel):
    pupil_id: str
    topic: str = Field(..., min_length=1, max_length=255)
    lesson_date: Optional[datetime] = None


class LessonUpdate(BaseModel):
    topic: Optional[str] = Field(default=None, min_length=1, max_length=255)
    lesson_date: Optional[datetime] = None
    status: Optional[Literal["draft", "recording_uploaded", "transcribing", "transcript_ready", "generating_documents", "completed", "failed"]] = None


class LessonResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    pupil_id: str
    teacher_id: str
    topic: str
    lesson_date: datetime
    status: str
    created_at: datetime
    updated_at: datetime


class LessonAudioRecordingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    lesson_id: str
    filename: str
    content_type: str
    size_bytes: int
    duration_seconds: Optional[float] = None
    sha256_checksum: Optional[str] = None
    status: str
    created_at: datetime
    updated_at: datetime


class LessonTranscribeRequest(BaseModel):
    recording_id: Optional[str] = None
    language: Optional[str] = Field(default=None, min_length=2, max_length=20)


class LessonTranscriptUpdate(BaseModel):
    edited_text: str = Field(min_length=1, max_length=200_000)
    review_status: Literal["needs_review", "reviewed"] = "reviewed"


class LessonTranscriptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    lesson_id: str
    recording_id: str
    provider: str
    language: str
    text: Optional[str] = None
    edited_text: Optional[str] = None
    review_status: str = "unreviewed"
    reviewed_at: Optional[datetime] = None
    status: str
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class LessonDocumentGenerateRequest(BaseModel):
    transcript_id: Optional[str] = None
    document_types: list[Literal["check_list", "pupil_mistakes"]] = Field(default_factory=list)


class LessonGeneratedDocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    lesson_id: str
    transcript_id: str
    document_type: str
    title: str
    filename: str
    content_type: str
    status: str
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    download_url: Optional[str] = None


class LessonProcessingJobCreate(BaseModel):
    job_type: Literal["full_pipeline", "transcribe", "generate_documents"] = "full_pipeline"
    recording_id: Optional[str] = None
    transcript_id: Optional[str] = None
    document_types: list[Literal["check_list", "pupil_mistakes"]] = Field(default_factory=list)


class LessonProcessingJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    lesson_id: str
    teacher_id: str
    job_type: str
    status: str
    stage: str
    recording_id: Optional[str] = None
    transcript_id: Optional[str] = None
    document_types: list[str] = Field(default_factory=list)
    document_ids: list[str] = Field(default_factory=list)
    error_message: Optional[str] = None
    attempts: int
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


# Compile Schemas
class CompileRequest(BaseModel):
    project_id: str
    main_file_name: Optional[str] = None
    main_file_content: Optional[str] = None
    all_files: Optional[dict[str, str]] = None


class RawCompileRequest(BaseModel):
    content: str
    files: dict[str, str] = Field(default_factory=dict)


class LatexCompileResult(BaseModel):
    """Typed boundary between compiler services and API routers."""

    status: Literal["success", "error"]
    output: Optional[str] = None
    error: Optional[str] = None
    compile_time: Optional[str] = None
    pdf_url: Optional[str] = None


class CompileResponse(BaseModel):
    status: str  # success, error
    output: Optional[str] = None
    error: Optional[str] = None
    compile_time: Optional[str] = None
    pdf_url: Optional[str] = None
    history_id: Optional[str] = None


class CompileHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    status: str
    output: Optional[str] = None
    error: Optional[str] = None
    compile_time: Optional[str] = None
    created_at: datetime


# Export Schemas
class ExportRequest(BaseModel):
    project_id: str
    format: str  # pdf, html, tex
    content: Optional[dict[str, str]] = None


class PDFGenerationResult(BaseModel):
    """Typed boundary between PDF export services and API routers."""

    success: bool
    filename: Optional[str] = None
    size: Optional[int] = None
    error: Optional[str] = None


class ExportResponse(BaseModel):
    url: str
    filename: str
    format: str
    size: Optional[int] = None


# Template Schemas
class TemplateResponse(BaseModel):
    id: str
    name: str
    description: str
    category: str
    content: str
    preview_image: Optional[str] = None


# Generation Schemas
class GenerationFields(BaseModel):
    level: str = "ЕГЭ"
    language: str = "русский"
    content_source_mode: Literal["materials_only", "ai_creative"] = "materials_only"
    latex_mode: Literal["safe", "rich"] = "safe"
    alpha_code: int = Field(1, ge=0, le=2)
    beta_code: int = Field(1, ge=0, le=50)
    gamma_code: int = Field(4, ge=1, le=5)
    grade: str = "11 класс"
    student_name: str = ""
    subject: str = "математика"
    topic: str = ""
    priority_method: str = "нейросеть выбирает самостоятельно по отношению к уровню и классу"
    graph_analytic: str = "по ситуации"


class GenerationRequest(BaseModel):
    provider: str = "ollama"
    model: Optional[str] = None
    fields: GenerationFields = Field(default_factory=GenerationFields)
    materials: str = ""
    project_id: Optional[str] = None


class GenerationPromptResponse(BaseModel):
    status: str
    prompt: str
    warnings: list[str] = Field(default_factory=list)
    provider: str
    model: Optional[str] = None


class GenerationValidationRequest(BaseModel):
    latex_code: str


class GenerationValidationResponse(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class GenerationProviderStatusResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    provider: str
    model: str
    available: bool
    message: str
    models: list[str] = Field(default_factory=list)
    model_available: Optional[bool] = None


class GenerationCompileCheckResponse(BaseModel):
    attempted: bool = False
    success: bool = False
    attempts: int = 0
    repaired: bool = False
    skipped_reason: Optional[str] = None
    error: Optional[str] = None


class GenerationTokenUsageResponse(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    source: str = "estimated"


class GenerationResultResponse(GenerationPromptResponse):
    latex_code: str
    raw_output: str
    validation: GenerationValidationResponse
    compile_check: GenerationCompileCheckResponse = Field(default_factory=GenerationCompileCheckResponse)
    token_usage: GenerationTokenUsageResponse = Field(default_factory=GenerationTokenUsageResponse)


class GenerationPresetResponse(BaseModel):
    id: str
    name: str
    description: str
    defaults: dict[str, Any]


class GenerationHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: Optional[str] = None
    provider: str
    model: Optional[str] = None
    status: str
    prompt_hash: str
    prompt_preview: Optional[str] = None
    raw_output_hash: Optional[str] = None
    latex_code_hash: Optional[str] = None
    latex_code_preview: Optional[str] = None
    fields: dict[str, Any] = Field(default_factory=dict)
    validation: Optional[dict[str, Any]] = None
    compile_check: Optional[dict[str, Any]] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    token_count_source: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime


# Snapshot Schemas
class SnapshotCreate(BaseModel):
    project_id: Optional[str] = None
    name: str = "Автосохранение"
    data: dict[str, Any] = Field(default_factory=dict)


class SnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    name: str
    created_at: datetime


# Readiness Schemas
class ReadinessCheckResponse(BaseModel):
    status: Literal["ok", "missing", "skipped", "error"]
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ReadinessResponse(BaseModel):
    status: Literal["ready", "degraded", "not_ready"]
    checks: dict[str, ReadinessCheckResponse]


# Generic
class MessageResponse(BaseModel):
    message: str


class ErrorResponse(BaseModel):
    detail: str


class PaginationResponse(BaseModel):
    total: int
    page: int
    per_page: int
    items: list[Any] = Field(default_factory=list)
