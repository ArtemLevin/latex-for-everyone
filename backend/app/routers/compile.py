import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from app.models import Project, CompileHistory, CompileJob
from app.dependencies import get_current_user_id
from app.schemas import (
    CompileJobResponse,
    CompileRequest,
    CompileResponse,
    CompileHistoryResponse,
    LatexCompileResult,
    RawCompileRequest,
)
from app.services.artifact_paths import (
    ArtifactPathError,
    UnsupportedArtifactTypeError,
    resolve_artifact_download,
)
from app.services.artifact_service import (
    ArtifactCreationError,
    ArtifactExpiredError,
    ArtifactMissingFileError,
    ArtifactNotFoundError,
    create_artifact_record,
    find_authorized_artifact_by_storage_filename,
    mark_artifact_accessed,
    safe_original_filename,
)
from app.services.compile_control import CompileControlService, CompileQueueFullError, CompileRateLimitError
from app.services.compile_jobs import CompileJobService
from app.services.latex_compiler import LatexCompiler
from app.services.latex_file_policy import (
    LatexFilePolicyError,
    enforce_latex_file_policy,
    parse_allowed_extensions,
    validate_latex_filename,
)
from app.services.payload_limits import PayloadLimitError, enforce_latex_payload_limits
from sqlalchemy.orm import Session
from app.database import get_db
from fastapi.responses import FileResponse
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

compiler = LatexCompiler()
compile_control = CompileControlService()
compile_job_service = CompileJobService()


def create_compile_pdf_artifact(
    db: Session,
    *,
    owner_id: str,
    result: LatexCompileResult,
    project_id: str | None = None,
    compile_history_id: str | None = None,
    original_filename: str = "main.pdf",
):
    if result.status != "success" or not result.pdf_filename:
        return None
    source = resolve_artifact_download("compile_pdf", result.pdf_filename).path
    return create_artifact_record(
        db,
        owner_id=owner_id,
        project_id=project_id,
        compile_history_id=compile_history_id,
        kind="compile_pdf",
        format="pdf",
        storage_root="compile_pdf",
        source_path=source,
        original_filename=original_filename,
        content_disposition_type="inline",
    )


def file_response_for_artifact_download(db: Session, download):
    mark_artifact_accessed(db, artifact=download.artifact)
    return FileResponse(
        path=str(download.target.path),
        filename=download.artifact.original_filename,
        media_type=download.artifact.media_type,
        content_disposition_type=download.artifact.content_disposition_type,
    )


def get_request_client(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def enforce_compile_rate_limit(key: str) -> None:
    try:
        compile_control.check_rate_limit(key=key)
    except CompileRateLimitError as exc:
        raise HTTPException(
            status_code=429,
            detail=f"Compile rate limit exceeded. Try again in {exc.retry_after_seconds} seconds.",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc


async def run_latex_compile_checked(
    main_content: str,
    files: dict[str, str],
    *,
    main_filename: str | None = None,
) -> LatexCompileResult:
    try:
        if main_filename is None:
            raw_result = await compile_control.run_in_thread(compiler.compile, main_content, files)
        else:
            raw_result = await compile_control.run_in_thread(
                compiler.compile,
                main_content,
                files,
                main_filename=main_filename,
            )
    except CompileQueueFullError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return LatexCompileResult.model_validate(raw_result)


def compile_job_to_response(job: CompileJob) -> CompileJobResponse:
    result = job.result_payload or {}
    return CompileJobResponse(
        id=job.id,
        project_id=job.project_id,
        history_id=job.compile_history_id,
        compile_history_id=job.compile_history_id,
        status=job.status,
        stage=job.stage,
        pdf_url=result.get("pdf_url"),
        error=job.error_message or result.get("error"),
        output=result.get("output"),
        compile_time=result.get("compile_time"),
        pdf_artifact_id=job.pdf_artifact_id,
        attempts=job.attempts,
        cancel_requested=job.cancel_requested,
        queued_at=job.queued_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def prepare_project_compile_payload(
    request_body: CompileRequest,
    *,
    owner_id: str,
    db: Session,
) -> tuple[Project, str, str, dict[str, str]]:
    project = db.query(Project).filter(Project.id == request_body.project_id, Project.owner_id == owner_id).first()
    if not project:
        logger.warning("compile project not found project_id=%s", request_body.project_id)
        raise HTTPException(status_code=404, detail="Project not found")

    files = {f.name: f.content for f in project.files}
    if request_body.all_files:
        files.update(request_body.all_files)

    if request_body.main_file_name:
        try:
            main_file_name = validate_latex_filename(
                request_body.main_file_name,
                allowed_extensions=parse_allowed_extensions(settings.LATEX_ALLOWED_EXTENSIONS),
            )
        except LatexFilePolicyError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    else:
        main_file_name = None
    main_content = request_body.main_file_content

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
        raise HTTPException(status_code=400, detail="No main LaTeX file found")

    files[main_file_name] = main_content
    enforce_compile_payload_limits(files)
    return project, main_file_name, main_content, files


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


@router.post("/jobs", response_model=CompileJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_compile_job(
    request_body: CompileRequest,
    response: Response,
    owner_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    project, main_file_name, main_content, files = prepare_project_compile_payload(
        request_body, owner_id=owner_id, db=db
    )
    enforce_compile_rate_limit(f"owner:{owner_id}:/api/compile/jobs")
    history = CompileHistory(project_id=project.id, status="pending")
    db.add(history)
    db.flush()
    payload = {"main_content": main_content, "main_file_name": main_file_name, "files": files}
    job = CompileJob(
        owner_id=owner_id,
        project_id=project.id,
        compile_history_id=history.id,
        status="queued",
        stage="queued",
        main_file_name=main_file_name,
        request_payload=payload,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    response.headers["Location"] = f"/api/compile/jobs/{job.id}"
    logger.info("compile job enqueued job_id=%s owner_id=%s project_id=%s", job.id, owner_id, project.id)
    return compile_job_to_response(job)


@router.get("/jobs/{job_id}", response_model=CompileJobResponse)
async def get_compile_job(
    job_id: str,
    owner_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    job = compile_job_service.get_job(db, job_id=job_id, owner_id=owner_id)
    if not job:
        raise HTTPException(status_code=404, detail="Compile job not found")
    return compile_job_to_response(job)


@router.post("/jobs/{job_id}/cancel", response_model=CompileJobResponse)
async def cancel_compile_job(
    job_id: str,
    owner_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    job = compile_job_service.get_job(db, job_id=job_id, owner_id=owner_id)
    if not job:
        raise HTTPException(status_code=404, detail="Compile job not found")
    job = compile_job_service.cancel_job(db, job=job)
    return compile_job_to_response(job)


@router.post("/", response_model=CompileResponse)
async def compile_project(
    request_body: CompileRequest,
    request: Request,
    owner_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    logger.info(
        "compile project requested project_id=%s main_file_name=%s has_main_content=%s override_files=%s",
        request_body.project_id,
        request_body.main_file_name or "default",
        bool(request_body.main_file_content),
        len(request_body.all_files or {}),
    )
    project = db.query(Project).filter(Project.id == request_body.project_id, Project.owner_id == owner_id).first()
    if not project:
        logger.warning("compile project not found project_id=%s", request_body.project_id)
        raise HTTPException(status_code=404, detail="Project not found")

    # Get all files
    files = {}
    for f in project.files:
        files[f.name] = f.content

    # Override with request content if provided
    if request_body.all_files:
        files.update(request_body.all_files)

    # Find the compile entrypoint. The frontend passes the currently selected file
    # as main_file_name; otherwise we keep the historical is_main/main.tex fallback.
    if request_body.main_file_name:
        try:
            main_file_name = validate_latex_filename(
                request_body.main_file_name,
                allowed_extensions=parse_allowed_extensions(settings.LATEX_ALLOWED_EXTENSIONS),
            )
        except LatexFilePolicyError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    else:
        main_file_name = None
    main_content = request_body.main_file_content

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
            request_body.project_id,
            main_file_name,
            len(files),
        )
        raise HTTPException(status_code=400, detail="No main LaTeX file found")

    files[main_file_name] = main_content
    enforce_compile_payload_limits(files)
    enforce_compile_rate_limit(f"owner:{owner_id}:/api/compile")

    # Create history record
    history = CompileHistory(
        project_id=request_body.project_id,
        status="pending",
    )
    db.add(history)
    db.flush()
    logger.info(
        "compile history created project_id=%s history_id=%s main_file_name=%s files=%s",
        request_body.project_id,
        history.id,
        main_file_name,
        len(files),
    )

    # Compile
    result = await run_latex_compile_checked(main_content, files, main_filename=main_file_name)

    # Update history and create owner-scoped artifact record for successful PDFs.
    history.status = result.status
    history.output = result.output
    history.error = result.error
    history.compile_time = result.compile_time
    pdf_url = None
    try:
        artifact = create_compile_pdf_artifact(
            db,
            owner_id=owner_id,
            project_id=project.id,
            compile_history_id=history.id,
            result=result,
            original_filename=safe_original_filename(f"{project.name}.pdf", format="pdf"),
        )
        if artifact is not None:
            pdf_url = artifact.download_url
        db.commit()
    except (ArtifactCreationError, ArtifactPathError):
        db.rollback()
        logger.exception("compile artifact creation failed project_id=%s history_id=%s", project.id, history.id)
        raise HTTPException(status_code=500, detail="Compile artifact could not be registered")
    logger.info(
        "compile project completed project_id=%s history_id=%s main_file_name=%s status=%s compile_time=%s pdf_url=%s",
        request_body.project_id,
        history.id,
        main_file_name,
        result.status,
        result.compile_time,
        pdf_url,
    )

    return CompileResponse(
        status=result.status,
        output=result.output,
        error=result.error,
        compile_time=result.compile_time,
        pdf_url=pdf_url,
        history_id=history.id,
    )


@router.post("/raw", response_model=CompileResponse)
async def compile_raw_latex(
    request_body: RawCompileRequest,
    request: Request,
    owner_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    logger.info("compile raw requested content_chars=%s files=%s", len(request_body.content), len(request_body.files))
    files_for_limits = {"__entrypoint__.tex": request_body.content, **request_body.files}
    enforce_compile_payload_limits(files_for_limits)
    enforce_compile_rate_limit(f"owner:{owner_id}:/api/compile/raw")
    result = await run_latex_compile_checked(request_body.content, request_body.files)
    pdf_url = None
    try:
        artifact = create_compile_pdf_artifact(
            db,
            owner_id=owner_id,
            result=result,
            original_filename="raw-compile.pdf",
        )
        if artifact is not None:
            pdf_url = artifact.download_url
        db.commit()
    except (ArtifactCreationError, ArtifactPathError):
        db.rollback()
        logger.exception("raw compile artifact creation failed owner_id=%s", owner_id)
        raise HTTPException(status_code=500, detail="Compile artifact could not be registered")

    logger.info(
        "compile raw completed status=%s compile_time=%s pdf_url=%s",
        result.status,
        result.compile_time,
        pdf_url,
    )

    return CompileResponse(
        status=result.status,
        output=result.output,
        error=result.error,
        compile_time=result.compile_time,
        pdf_url=pdf_url,
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
    history = (
        db.query(CompileHistory)
        .join(Project)
        .filter(CompileHistory.id == history_id, Project.owner_id == owner_id)
        .first()
    )
    if not history:
        raise HTTPException(status_code=404, detail="Compile history not found")
    return history


@router.get("/download/{filename}", deprecated=True)
async def download_compiled_pdf(
    filename: str,
    owner_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    logger.info("legacy compile pdf download requested filename=%s owner_id=%s", filename, owner_id)
    try:
        resolve_artifact_download("compile_pdf", filename)
        download = find_authorized_artifact_by_storage_filename(
            db,
            owner_id=owner_id,
            kind="compile_pdf",
            storage_filename=filename,
        )
    except UnsupportedArtifactTypeError as exc:
        raise HTTPException(status_code=400, detail="Unsupported compile artifact file type") from exc
    except ArtifactPathError as exc:
        raise HTTPException(status_code=400, detail="Invalid PDF filename") from exc
    except ArtifactExpiredError as exc:
        db.commit()
        raise HTTPException(status_code=410, detail="Artifact expired") from exc
    except ArtifactMissingFileError as exc:
        db.commit()
        raise HTTPException(status_code=404, detail="Artifact file not found") from exc
    except ArtifactNotFoundError as exc:
        raise HTTPException(status_code=404, detail="PDF not found") from exc

    return file_response_for_artifact_download(db, download)
