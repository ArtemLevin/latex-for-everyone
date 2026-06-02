from fastapi import APIRouter, Depends, HTTPException
from app.models import Project, CompileHistory
from app.schemas import CompileRequest, CompileResponse, CompileHistoryResponse, RawCompileRequest
from app.services.latex_compiler import LatexCompiler
from sqlalchemy.orm import Session
from app.database import get_db
from fastapi.responses import FileResponse
from pathlib import Path
from app.config import settings

router = APIRouter()

compiler = LatexCompiler()


@router.post("/", response_model=CompileResponse)
async def compile_project(
    request: CompileRequest,
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == request.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Get all files
    files = {}
    for f in project.files:
        files[f.name] = f.content

    # Override with request content if provided
    if request.all_files:
        files.update(request.all_files)

    # Find main file
    main_content = None
    if request.main_file_content:
        main_content = request.main_file_content
    else:
        main_file = next((f for f in project.files if f.is_main), None)
        if main_file:
            main_content = main_file.content
        else:
            # Try main.tex
            main_content = files.get("main.tex", "")

    if not main_content:
        raise HTTPException(status_code=400, detail="No main LaTeX file found")

    # Create history record
    history = CompileHistory(
        project_id=request.project_id,
        status="pending",
    )
    db.add(history)
    db.flush()

    # Compile
    result = compiler.compile(main_content, files)

    # Update history
    history.status = result["status"]
    history.output = result.get("output")
    history.error = result.get("error")
    history.compile_time = result.get("compile_time")
    db.commit()

    return CompileResponse(
        status=result["status"],
        output=result.get("output"),
        error=result.get("error"),
        compile_time=result.get("compile_time"),
        pdf_url=result.get("pdf_url"),
        history_id=history.id,
    )


@router.post("/raw", response_model=CompileResponse)
async def compile_raw_latex(request: RawCompileRequest):
    result = compiler.compile(request.content, request.files)

    return CompileResponse(
        status=result["status"],
        output=result.get("output"),
        error=result.get("error"),
        compile_time=result.get("compile_time"),
        pdf_url=result.get("pdf_url"),
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
    if not filename.endswith(".pdf") or Path(filename).name != filename:
        raise HTTPException(status_code=400, detail="Invalid PDF filename")

    filepath = Path(settings.COMPILE_WORK_DIR) / "pdfs" / filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="PDF not found")

    return FileResponse(
        path=str(filepath),
        filename=filename,
        media_type="application/pdf",
    )
