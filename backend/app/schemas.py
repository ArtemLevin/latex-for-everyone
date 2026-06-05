from datetime import datetime
from typing import Optional, Any
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


# Compile Schemas
class CompileRequest(BaseModel):
    project_id: str
    main_file_content: Optional[str] = None
    all_files: Optional[dict[str, str]] = None


class RawCompileRequest(BaseModel):
    content: str
    files: dict[str, str] = Field(default_factory=dict)


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


class GenerationResultResponse(GenerationPromptResponse):
    latex_code: str
    raw_output: str
    validation: GenerationValidationResponse


class GenerationPresetResponse(BaseModel):
    id: str
    name: str
    description: str
    defaults: dict[str, Any]


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
