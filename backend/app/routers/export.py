import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from app.config import settings
from app.models import Project
from app.schemas import ExportRequest, ExportResponse, PDFGenerationResult
from app.services.pdf_generator import PDFGenerator
from sqlalchemy.orm import Session
from app.database import get_db
from pathlib import Path, PurePosixPath

logger = logging.getLogger(__name__)

router = APIRouter()

pdf_generator = PDFGenerator()

EXPORT_MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".html": "text/html",
    ".zip": "application/zip",
}


def validate_export_entry_name(name: str) -> str:
    """Validate a ZIP entry name to prevent zip-slip/path traversal entries."""
    if not name or name.startswith(("/", "\\")) or "\\" in name:
        raise HTTPException(status_code=400, detail=f"Invalid export filename: {name}")

    path = PurePosixPath(name)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise HTTPException(status_code=400, detail=f"Invalid export filename: {name}")

    return path.as_posix()


@router.post("/pdf", response_model=ExportResponse)
async def export_pdf(
    request: ExportRequest,
    db: Session = Depends(get_db),
):
    logger.info("export pdf requested project_id=%s content_files=%s", request.project_id, len(request.content or {}))
    project = db.query(Project).filter(Project.id == request.project_id).first()
    if not project:
        logger.warning("export pdf project not found project_id=%s", request.project_id)
        raise HTTPException(status_code=404, detail="Project not found")

    # Get all files
    files = {}
    for f in project.files:
        files[f.name] = f.content

    if request.content:
        files.update(request.content)

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

    logger.info("export pdf completed project_id=%s filename=%s size=%s", request.project_id, result.filename, result.size)
    return ExportResponse(
        url=f"/api/export/download/{result.filename}",
        filename=result.filename,
        format="pdf",
        size=result.size,
    )


@router.post("/html", response_model=ExportResponse)
async def export_html(
    request: ExportRequest,
    db: Session = Depends(get_db),
):
    logger.info("export html requested project_id=%s content_files=%s", request.project_id, len(request.content or {}))
    project = db.query(Project).filter(Project.id == request.project_id).first()
    if not project:
        logger.warning("export html project not found project_id=%s", request.project_id)
        raise HTTPException(status_code=404, detail="Project not found")

    files = {}
    for f in project.files:
        files[f.name] = f.content

    if request.content:
        files.update(request.content)

    main_content = files.get("main.tex", "")
    if not main_content:
        main_content = next(iter(files.values()), "")

    html_content = pdf_generator.generate_html(main_content)

    output_dir = Path(settings.UPLOAD_DIR) / "exports"
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{project.id}_{project.name.replace(' ', '_')}.html"
    filepath = output_dir / filename

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
    db: Session = Depends(get_db),
):
    logger.info("export tex requested project_id=%s content_files=%s", request.project_id, len(request.content or {}))
    project = db.query(Project).filter(Project.id == request.project_id).first()
    if not project:
        logger.warning("export tex project not found project_id=%s", request.project_id)
        raise HTTPException(status_code=404, detail="Project not found")

    files = {}
    for f in project.files:
        files[f.name] = f.content

    if request.content:
        files.update(request.content)

    from zipfile import ZipFile

    output_dir = Path(settings.UPLOAD_DIR) / "exports"
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{project.id}_{project.name.replace(' ', '_')}.zip"
    filepath = output_dir / filename

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


def resolve_export_download_path(filename: str) -> tuple[Path, str]:
    """Return a safe export artifact path and media type for a download filename."""
    if Path(filename).name != filename:
        raise HTTPException(status_code=400, detail="Invalid export filename")

    suffix = Path(filename).suffix.lower()
    media_type = EXPORT_MEDIA_TYPES.get(suffix)
    if media_type is None:
        raise HTTPException(status_code=400, detail="Unsupported export file type")

    export_dir = (Path(settings.UPLOAD_DIR) / "exports").resolve()
    filepath = (export_dir / filename).resolve()

    # Resolve both paths before the prefix check so symlinks or crafted filenames
    # cannot escape the export directory configured for downloadable artifacts.
    if export_dir not in filepath.parents:
        raise HTTPException(status_code=400, detail="Invalid export filename")

    return filepath, media_type


@router.get("/download/{filename}")
async def download_export(filename: str):
    logger.info("export download requested filename=%s", filename)
    filepath, media_type = resolve_export_download_path(filename)

    if not filepath.is_file():
        logger.warning("export download missing filename=%s path=%s", filename, filepath)
        raise HTTPException(status_code=404, detail="File not found")

    logger.info("export download served filename=%s media_type=%s size=%s", filename, media_type, filepath.stat().st_size)
    return FileResponse(
        path=str(filepath),
        filename=filename,
        media_type=media_type,
    )
