"""
Celery worker for async compilation tasks.
Run with: celery -A app.worker.celery_app worker --loglevel=info
"""
from celery import Celery
from app.config import settings
from app.services.latex_compiler import LatexCompiler

celery_app = Celery(
    "latexed",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/0",
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Europe/Moscow",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=120,
    worker_max_tasks_per_child=100,
)


@celery_app.task(bind=True, max_retries=3)
def compile_task(self, main_content: str, files: dict, project_id: str) -> dict:
    """Async compilation task."""
    compiler = LatexCompiler()
    try:
        result = compiler.compile(main_content, files)
        return {
            "project_id": project_id,
            "status": result["status"],
            "compile_time": result.get("compile_time"),
            "error": result.get("error"),
        }
    except Exception as exc:
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)


@celery_app.task
def cleanup_old_compiles(max_age_hours: int = 24) -> int:
    """Clean up old compilation files."""
    import time
    from pathlib import Path

    work_dir = Path(settings.COMPILE_WORK_DIR)
    cutoff = time.time() - (max_age_hours * 3600)
    cleaned = 0

    for item in work_dir.iterdir():
        if item.is_dir() and item.stat().st_mtime < cutoff:
            import shutil
            shutil.rmtree(item, ignore_errors=True)
            cleaned += 1

    return cleaned
