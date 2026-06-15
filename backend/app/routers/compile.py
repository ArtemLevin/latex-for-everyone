import logging

from fastapi import APIRouter, Depends, HTTPException
from app.models import Project, CompileHistory
from app.dependencies import get_current_user_id
from app.schemas import CompileRequest, CompileResponse, CompileHistoryResponse, LatexCompileResult, RawCompileRequest
from app.services.artifact_paths import (
    ArtifactPathError,
    UnsupportedArtifactTypeError,
    resolve_artifact_download,
)
from app.services.latex_compiler import LatexCompiler
from app.services.latex_file_policy import LatexFilePolicyError, enforce_latex_file_policy, parse_allowed_extensions, validate_latex_filename
from app.services.payload_limits import PayloadLimitError, enforce_latex_payload_limits
from sqlalchemy.orm import Session
from app.database import get_db
from fastapi.responses import FileResponse
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

compiler = LatexCompiler()


def enforce_compile_payload_limits(files: dict[str, str]) -> None:
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
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PayloadLimitError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc


@router.post("/", response_model=CompileResponse)
async def compile_project(
    request: CompileRequest,
    owner_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    logger.info(
        "compile project requested project_id=%s main_file_name=%s has_main_content=%s override_files=%s",
        request.project_id,
        request.main_file_name or "default",
        bool(request.main_file_content),
        len(request.all_files or {}),
    )
    project = db.query(Project).filter(Project.id == request.project_id, Project.owner_id == owner_id).first()
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
    if request.main_file_name:
        try:
            main_file_name = validate_latex_filename(
                request.main_file_name,
                allowed_extensions=parse_allowed_extensions(settings.LATEX_ALLOWED_EXTENSIONS),
            )
        except LatexFilePolicyError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    else:
        main_file_name = None
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

    files[main_file_name] = main_content
    enforce_compile_payload_limits(files)

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
    files_for_limits = {"__entrypoint__.tex": request.content, **request.files}
    enforce_compile_payload_limits(files_for_limits)
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
    owner_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == project_id, Project.owner_id == owner_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
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
    owner_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    history = db.query(CompileHistory).join(Project).filter(CompileHistory.id == history_id, Project.owner_id == owner_id).first()
    if not history:
        raise HTTPException(status_code=404, detail="Compile history not found")
    return history


@router.get("/download/{filename}")
async def download_compiled_pdf(filename: str):
    logger.info("compile pdf download requested filename=%s", filename)
    try:
        target = resolve_artifact_download("compile_pdf", filename)
    except UnsupportedArtifactTypeError as exc:
        logger.warning("compile pdf download rejected unsupported filename=%s", filename)
        raise HTTPException(status_code=400, detail="Unsupported compile artifact file type") from exc
    except ArtifactPathError as exc:
        logger.warning("compile pdf download rejected invalid filename=%s", filename)
        raise HTTPException(status_code=400, detail="Invalid PDF filename") from exc

    if not target.path.is_file():
        logger.warning("compile pdf download missing filename=%s path=%s", filename, target.path)
        raise HTTPException(status_code=404, detail="PDF not found")

    logger.info("compile pdf download served filename=%s size=%s", filename, target.path.stat().st_size)
    return FileResponse(
        path=str(target.path),
        filename=target.filename,
        media_type=target.media_type,
        content_disposition_type=target.content_disposition_type,
    )
