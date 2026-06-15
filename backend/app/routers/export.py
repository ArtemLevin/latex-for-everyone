import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from app.config import settings
from app.dependencies import get_current_user_id
from app.models import Project
from app.schemas import ExportRequest, ExportResponse, PDFGenerationResult
from app.services.artifact_cleanup import cleanup_old_files
from app.services.artifact_paths import (
    ArtifactPathError,
    UnsupportedArtifactTypeError,
    export_root,
    resolve_artifact_download,
)
from app.services.latex_file_policy import LatexFilePolicyError, enforce_latex_file_policy, parse_allowed_extensions, validate_latex_filename
from app.services.pdf_generator import PDFGenerator
from app.services.payload_limits import PayloadLimitError, enforce_latex_payload_limits
from sqlalchemy.orm import Session
from app.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter()

pdf_generator = PDFGenerator()


def enforce_export_payload_limits(files: dict[str, str]) -> None:
    try:
        enforce_latex_file_policy(
            files,
            allowed_extensions=parse_allowed_extensions(settings.LATEX_ALLOWED_EXTENSIONS),
        )
        enforce_latex_payload_limits(
            files,
            max_files=settings.MAX_LATEX_FILES,
            max_file_chars=settings.MAX_LATEX_FILE_CHARS,
            max_total_chars=settings.MAX_LATEX_TOTAL_CHARS,
        )
    except LatexFilePolicyError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid export filename: {exc}") from exc
    except PayloadLimitError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc


def validate_export_entry_name(name: str) -> str:
    """Validate a ZIP entry name to prevent zip-slip/path traversal entries."""
    try:
        return validate_latex_filename(
            name,
            allowed_extensions=parse_allowed_extensions(settings.LATEX_ALLOWED_EXTENSIONS),
        )
    except LatexFilePolicyError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid export filename: {exc}") from exc


@router.post("/pdf", response_model=ExportResponse)
async def export_pdf(
    request: ExportRequest,
    owner_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    logger.info("export pdf requested project_id=%s content_files=%s", request.project_id, len(request.content or {}))
    project = db.query(Project).filter(Project.id == request.project_id, Project.owner_id == owner_id).first()
    if not project:
        logger.warning("export pdf project not found project_id=%s", request.project_id)
        raise HTTPException(status_code=404, detail="Project not found")

    # Get all files
    files = {}
    for f in project.files:
        files[f.name] = f.content

    if request.content:
        files.update(request.content)

    enforce_export_payload_limits(files)

    main_content = files.get("main.tex", "")
    if not main_content:
        main_content = next(iter(files.values()), "")

    result = PDFGenerationResult.model_validate(pdf_generator.generate_pdf(main_content, files))

    if not result.success:
        logger.warning("export pdf failed project_id=%s error=%s", request.project_id, result.error)
        raise HTTPException(status_code=500, detail=result.error or "PDF export failed")
    if not result.filename:
        logger.error("export pdf succeeded without filename project_id=%s", request.project_id)
        raise HTTPException(status_code=500, detail="PDF export did not return a filename")

    try:
        target = resolve_artifact_download("export", result.filename)
    except ArtifactPathError as exc:
        logger.error("export pdf produced unsafe filename project_id=%s filename=%s", request.project_id, result.filename)
        raise HTTPException(status_code=500, detail="PDF export produced an invalid artifact filename") from exc

    logger.info("export pdf completed project_id=%s filename=%s size=%s", request.project_id, target.filename, result.size)
    return ExportResponse(
        url=f"/api/export/download/{target.filename}",
        filename=target.filename,
        format="pdf",
        size=result.size,
    )


@router.post("/html", response_model=ExportResponse)
async def export_html(
    request: ExportRequest,
    owner_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    logger.info("export html requested project_id=%s content_files=%s", request.project_id, len(request.content or {}))
    project = db.query(Project).filter(Project.id == request.project_id, Project.owner_id == owner_id).first()
    if not project:
        logger.warning("export html project not found project_id=%s", request.project_id)
        raise HTTPException(status_code=404, detail="Project not found")

    files = {}
    for f in project.files:
        files[f.name] = f.content

    if request.content:
        files.update(request.content)

    enforce_export_payload_limits(files)

    main_content = files.get("main.tex", "")
    if not main_content:
        main_content = next(iter(files.values()), "")

    html_content = pdf_generator.generate_html(main_content)

    output_dir = export_root()
    output_dir.mkdir(parents=True, exist_ok=True)
    cleanup_old_files(
        output_dir,
        max_age_seconds=settings.ARTIFACT_TTL_SECONDS,
        suffixes={".pdf", ".html", ".zip"},
        trusted_roots=(output_dir,),
    )

    filename = f"{project.id}.html"
    filepath = resolve_artifact_download("export", filename).path

    filepath.write_text(html_content, encoding="utf-8")

    size = filepath.stat().st_size
    logger.info("export html completed project_id=%s filename=%s size=%s", request.project_id, filename, size)
    return ExportResponse(
        url=f"/api/export/download/{filename}",
        filename=filename,
        format="html",
        size=size,
    )


@router.post("/tex", response_model=ExportResponse)
async def export_tex(
    request: ExportRequest,
    owner_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    logger.info("export tex requested project_id=%s content_files=%s", request.project_id, len(request.content or {}))
    project = db.query(Project).filter(Project.id == request.project_id, Project.owner_id == owner_id).first()
    if not project:
        logger.warning("export tex project not found project_id=%s", request.project_id)
        raise HTTPException(status_code=404, detail="Project not found")

    files = {}
    for f in project.files:
        files[f.name] = f.content

    if request.content:
        files.update(request.content)

    enforce_export_payload_limits(files)

    from zipfile import ZipFile

    output_dir = export_root()
    output_dir.mkdir(parents=True, exist_ok=True)
    cleanup_old_files(
        output_dir,
        max_age_seconds=settings.ARTIFACT_TTL_SECONDS,
        suffixes={".pdf", ".html", ".zip"},
        trusted_roots=(output_dir,),
    )

    filename = f"{project.id}.zip"
    filepath = resolve_artifact_download("export", filename).path

    with ZipFile(filepath, "w") as zf:
        for name, content in files.items():
            zf.writestr(validate_export_entry_name(name), content)

    size = filepath.stat().st_size
    logger.info("export tex completed project_id=%s filename=%s files=%s size=%s", request.project_id, filename, len(files), size)
    return ExportResponse(
        url=f"/api/export/download/{filename}",
        filename=filename,
        format="tex",
        size=size,
    )


@router.get("/download/{filename}")
async def download_export(filename: str):
    logger.info("export download requested filename=%s", filename)
    try:
        target = resolve_artifact_download("export", filename)
    except UnsupportedArtifactTypeError as exc:
        raise HTTPException(status_code=400, detail="Unsupported export file type") from exc
    except ArtifactPathError as exc:
        raise HTTPException(status_code=400, detail="Invalid export filename") from exc

    if not target.path.is_file():
        logger.warning("export download missing filename=%s path=%s", filename, target.path)
        raise HTTPException(status_code=404, detail="File not found")

    logger.info("export download served filename=%s media_type=%s size=%s", filename, target.media_type, target.path.stat().st_size)
    return FileResponse(
        path=str(target.path),
        filename=target.filename,
        media_type=target.media_type,
    )
