import logging

from sqlalchemy.orm import Session

from app.models import CompileHistory
from app.schemas import LatexCompileResult
from app.services.artifact_paths import resolve_artifact_download
from app.services.artifact_service import create_artifact_record, safe_original_filename
from app.services.compile_jobs import CompileJobService
from app.services.compile_runners import CompileInput, create_compile_runner

logger = logging.getLogger(__name__)


class CompileJobWorkerService:
    def __init__(self, job_service: CompileJobService | None = None) -> None:
        self.job_service = job_service or CompileJobService()

    def run_claimed_job(self, db: Session, *, job_id: str, worker_id: str) -> None:
        job = self.job_service.get_job(db, job_id=job_id)
        if job is None or job.worker_id != worker_id or job.status != "running":
            return
        if job.cancel_requested:
            self.job_service.cancel_job(db, job=job)
            return
        payload = job.request_payload or {}
        try:
            job.stage = "running_pdflatex_pass_1"
            db.add(job)
            db.commit()
            runner = create_compile_runner()
            output = runner.compile(
                CompileInput(
                    main_content=payload["main_content"],
                    files=payload.get("files") or {},
                    main_filename=payload.get("main_file_name") or job.main_file_name,
                )
            )
            result = LatexCompileResult(
                status=output.status,
                output=output.output,
                error=output.error,
                compile_time=output.compile_time,
                pdf_filename=output.pdf_filename,
                pdf_url=f"/api/compile/download/{output.pdf_filename}" if output.pdf_filename else None,
            )
            history = db.query(CompileHistory).filter(CompileHistory.id == job.compile_history_id).first()
            if history:
                history.status = result.status
                history.output = result.output
                history.error = result.error
                history.compile_time = result.compile_time
                db.add(history)
                db.commit()
            artifact_id = None
            pdf_url = None
            if result.status == "success" and result.pdf_filename and not job.cancel_requested:
                job.stage = "collecting_artifacts"
                db.add(job)
                db.commit()
                target = resolve_artifact_download("compile_pdf", result.pdf_filename)
                artifact = create_artifact_record(
                    db,
                    owner_id=job.owner_id,
                    project_id=job.project_id,
                    compile_history_id=job.compile_history_id,
                    kind="compile_pdf",
                    format="pdf",
                    storage_root="compile_pdf",
                    source_path=target.path,
                    original_filename=safe_original_filename("compile.pdf", format="pdf"),
                    content_disposition_type="inline",
                )
                artifact_id = artifact.id
                pdf_url = artifact.download_url
            result_payload = {
                "status": result.status,
                "output": result.output,
                "error": result.error,
                "compile_time": result.compile_time,
                "pdf_url": pdf_url,
            }
            if job.cancel_requested:
                self.job_service.cancel_job(db, job=job)
                return
            if result.status == "success":
                self.job_service.mark_completed(db, job=job, result_payload=result_payload, pdf_artifact_id=artifact_id)
            else:
                self.job_service.mark_failed(
                    db, job=job, error_message=result.error or "Compilation failed", result_payload=result_payload
                )
        except Exception as exc:
            logger.exception("compile job failed job_id=%s worker_id=%s", job_id, worker_id)
            self.job_service.mark_failed(
                db, job=job, error_message=str(exc), result_payload={"status": "error", "error": str(exc)}
            )
