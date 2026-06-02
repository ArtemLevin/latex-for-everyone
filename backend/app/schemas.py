from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, Field


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
    id: str
    project_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


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
    id: str
    owner_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    settings: dict[str, Any] = {}

    class Config:
        from_attributes = True


class ProjectDetailResponse(ProjectResponse):
    files: list[FileResponse] = []


# Compile Schemas
class CompileRequest(BaseModel):
    project_id: str
    main_file_content: Optional[str] = None
    all_files: Optional[dict[str, str]] = None


class CompileResponse(BaseModel):
    status: str  # success, error
    output: Optional[str] = None
    error: Optional[str] = None
    compile_time: Optional[str] = None
    pdf_url: Optional[str] = None
    history_id: Optional[str] = None


class CompileHistoryResponse(BaseModel):
    id: str
    project_id: str
    status: str
    output: Optional[str] = None
    error: Optional[str] = None
    compile_time: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


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


# Snapshot Schemas
class SnapshotCreate(BaseModel):
    project_id: str
    name: Optional[str] = "Автосохранение"
    data: dict[str, Any]


class SnapshotResponse(BaseModel):
    id: str
    project_id: str
    name: str
    created_at: datetime

    class Config:
        from_attributes = True


# Generic
class MessageResponse(BaseModel):
    message: str


class ErrorResponse(BaseModel):
    detail: str


class PaginationResponse(BaseModel):
    total: int
    page: int
    per_page: int
    items: list[Any] = []
