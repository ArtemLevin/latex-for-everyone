import logging

from fastapi import APIRouter, Depends, HTTPException
from app.models import Project, CompileHistory
from app.schemas import CompileRequest, CompileResponse, CompileHistoryResponse, LatexCompileResult, RawCompileRequest
from app.services.latex_compiler import LatexCompiler
from sqlalchemy.orm import Session
from app.database import get_db
from fastapi.responses import FileResponse
from pathlib import Path
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

compiler = LatexCompiler()


@router.post("/", response_model=CompileResponse)
async def compile_project(
    request: CompileRequest,
    db: Session = Depends(get_db),
):
    logger.info(
        "compile project requested project_id=%s main_file_name=%s has_main_content=%s override_files=%s",
        request.project_id,
        request.main_file_name or "default",
        bool(request.main_file_content),
        len(request.all_files or {}),
    )
    project = db.query(Project).filter(Project.id == request.project_id).first()
    if not project:
        logger.warning("compile project not found project_id=%s", request.project_id)
        raise HTTPException(status_code=404, detail="Project not found")

    # Get all files
    files = {}
    for f in project.files:
        files[f.name] = f.content

    # Override with request content if provided
    if request.all_files:
        files.update(request.all_files)

    # Find the compile entrypoint. The frontend passes the currently selected file
    # as main_file_name; otherwise we keep the historical is_main/main.tex fallback.
    main_file_name = Path(request.main_file_name).name if request.main_file_name else None
    main_content = request.main_file_content

    if main_file_name and main_content is None:
        main_content = files.get(main_file_name)

    if not main_file_name:
        main_file = next((f for f in project.files if f.is_main), None)
        if main_file:
            main_file_name = main_file.name
            main_content = main_content if main_content is not None else main_file.content
        else:
            main_file_name = "main.tex"
            main_content = main_content if main_content is not None else files.get(main_file_name, "")

    if main_content is None:
        main_content = files.get(main_file_name, "")

    if not main_content:
        logger.warning(
            "compile project missing main file project_id=%s main_file_name=%s files=%s",
            request.project_id,
            main_file_name,
            len(files),
        )
        raise HTTPException(status_code=400, detail="No main LaTeX file found")

    # Create history record
    history = CompileHistory(
        project_id=request.project_id,
        status="pending",
    )
    db.add(history)
    db.flush()
    logger.info("compile history created project_id=%s history_id=%s main_file_name=%s files=%s", request.project_id, history.id, main_file_name, len(files))

    # Compile
    result = LatexCompileResult.model_validate(compiler.compile(main_content, files, main_filename=main_file_name))

    # Update history
    history.status = result.status
    history.output = result.output
    history.error = result.error
    history.compile_time = result.compile_time
    db.commit()
    logger.info(
        "compile project completed project_id=%s history_id=%s main_file_name=%s status=%s compile_time=%s pdf_url=%s",
        request.project_id,
        history.id,
        main_file_name,
        result.status,
        result.compile_time,
        result.pdf_url,
    )

    return CompileResponse(
        status=result.status,
        output=result.output,
        error=result.error,
        compile_time=result.compile_time,
        pdf_url=result.pdf_url,
        history_id=history.id,
    )


@router.post("/raw", response_model=CompileResponse)
async def compile_raw_latex(request: RawCompileRequest):
    logger.info("compile raw requested content_chars=%s files=%s", len(request.content), len(request.files))
    result = LatexCompileResult.model_validate(compiler.compile(request.content, request.files))
    logger.info(
        "compile raw completed status=%s compile_time=%s pdf_url=%s",
        result.status,
        result.compile_time,
        result.pdf_url,
    )

    return CompileResponse(
        status=result.status,
        output=result.output,
        error=result.error,
        compile_time=result.compile_time,
        pdf_url=result.pdf_url,
    )


@router.get("/history/project/{project_id}", response_model=list[CompileHistoryResponse])
@router.get("/history/{project_id}", response_model=list[CompileHistoryResponse], deprecated=True)
async def get_compile_history(
    project_id: str,
    limit: int = 20,
    db: Session = Depends(get_db),
):
    history = (
        db.query(CompileHistory)
        .filter(CompileHistory.project_id == project_id)
        .order_by(CompileHistory.created_at.desc())
        .limit(limit)
        .all()
    )
    return history


@router.get("/history/item/{history_id}", response_model=CompileHistoryResponse)
@router.get("/history/detail/{history_id}", response_model=CompileHistoryResponse, deprecated=True)
async def get_compile_history_detail(
    history_id: str,
    db: Session = Depends(get_db),
):
    history = db.query(CompileHistory).filter(CompileHistory.id == history_id).first()
    if not history:
        raise HTTPException(status_code=404, detail="Compile history not found")
    return history


@router.get("/download/{filename}")
async def download_compiled_pdf(filename: str):
    logger.info("compile pdf download requested filename=%s", filename)
    if not filename.endswith(".pdf") or Path(filename).name != filename:
        logger.warning("compile pdf download rejected invalid filename=%s", filename)
        raise HTTPException(status_code=400, detail="Invalid PDF filename")

    filepath = Path(settings.COMPILE_WORK_DIR) / "pdfs" / filename
    if not filepath.exists():
        logger.warning("compile pdf download missing filename=%s path=%s", filename, filepath)
        raise HTTPException(status_code=404, detail="PDF not found")

    logger.info("compile pdf download served filename=%s size=%s", filename, filepath.stat().st_size)
    return FileResponse(
        path=str(filepath),
        filename=filename,
        media_type="application/pdf",
    )
