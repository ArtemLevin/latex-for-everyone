from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from app.models import Project
from app.schemas import ExportRequest, ExportResponse
from app.services.pdf_generator import PDFGenerator
from sqlalchemy.orm import Session
from app.database import get_db
from pathlib import Path

router = APIRouter()

pdf_generator = PDFGenerator()


@router.post("/pdf", response_model=ExportResponse)
async def export_pdf(
    request: ExportRequest,
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == request.project_id).first()
    if not project:
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

    result = pdf_generator.generate_pdf(main_content, files)

    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["error"])

    return ExportResponse(
        url=f"/api/export/download/{result['filename']}",
        filename=result["filename"],
        format="pdf",
        size=result.get("size"),
    )


@router.post("/html", response_model=ExportResponse)
async def export_html(
    request: ExportRequest,
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == request.project_id).first()
    if not project:
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

    from app.config import settings
    output_dir = Path(settings.UPLOAD_DIR) / "exports"
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{project.id}_{project.name.replace(' ', '_')}.html"
    filepath = output_dir / filename

    filepath.write_text(html_content, encoding="utf-8")

    return ExportResponse(
        url=f"/api/export/download/{filename}",
        filename=filename,
        format="html",
        size=filepath.stat().st_size,
    )


@router.post("/tex", response_model=ExportResponse)
async def export_tex(
    request: ExportRequest,
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == request.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    files = {}
    for f in project.files:
        files[f.name] = f.content

    if request.content:
        files.update(request.content)

    from app.config import settings
    from zipfile import ZipFile

    output_dir = Path(settings.UPLOAD_DIR) / "exports"
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{project.id}_{project.name.replace(' ', '_')}.zip"
    filepath = output_dir / filename

    with ZipFile(filepath, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)

    return ExportResponse(
        url=f"/api/export/download/{filename}",
        filename=filename,
        format="tex",
        size=filepath.stat().st_size,
    )


@router.get("/download/{filename}")
async def download_export(filename: str):
    from app.config import settings

    filepath = Path(settings.UPLOAD_DIR) / "exports" / filename

    if not filepath.exists():
        raise HTTPException(status_code=404, detail="File not found")

    media_type = "application/octet-stream"
    if filename.endswith(".pdf"):
        media_type = "application/pdf"
    elif filename.endswith(".html"):
        media_type = "text/html"
    elif filename.endswith(".zip"):
        media_type = "application/zip"

    return FileResponse(
        path=str(filepath),
        filename=filename,
        media_type=media_type,
    )
