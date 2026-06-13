import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import inspect, text

from app.config import settings
from app.database import Base, engine
from app.logging_config import configure_logging, reset_request_id, set_request_id
from app.routers import compile, export, files, generation, lessons, projects, pupils, templates
from app.schemas import ReadinessResponse
from app.services import readiness


# Logging
configure_logging()
logger = logging.getLogger(__name__)




LESSON_WORKFLOW_COMPAT_TABLE_COLUMNS = {
    "lesson_audio_recordings": {
        "duration_seconds": "FLOAT",
        "sha256_checksum": "VARCHAR(64)",
    },
    "lesson_transcripts": {
        "edited_text": "TEXT",
        "review_status": "VARCHAR(50) DEFAULT 'unreviewed'",
        "reviewed_at": "DATETIME",
    },
    "lesson_processing_jobs": {
        "document_types": "JSON DEFAULT '[]'",
    },
}

LESSON_WORKFLOW_COMPAT_INDEXES = {
    "lesson_audio_recordings": {
        "ix_lesson_audio_recordings_sha256_checksum": "sha256_checksum",
    },
    "lesson_transcripts": {
        "ix_lesson_transcripts_review_status": "review_status",
    },
}

GENERATION_HISTORY_COMPAT_COLUMNS = {
    "input_tokens": "INTEGER",
    "output_tokens": "INTEGER",
    "total_tokens": "INTEGER",
    "token_count_source": "VARCHAR(50)",
}


def ensure_generation_history_compat_columns() -> None:
    """Patch local/dev SQLite-style schemas that predate token-usage migrations.

    SQLAlchemy create_all() intentionally does not ALTER existing tables, so older
    local databases can miss columns added by newer Alembic revisions. Production
    should still run Alembic with AUTO_CREATE_TABLES=false; this helper only keeps
    the default local/dev auto-create path from crashing on stale SQLite files.
    """
    inspector = inspect(engine)
    if "generation_history" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("generation_history")}
    missing_columns = {
        name: definition
        for name, definition in GENERATION_HISTORY_COMPAT_COLUMNS.items()
        if name not in existing_columns
    }
    if not missing_columns:
        return

    logger.warning(
        "database auto-create found stale generation_history schema; adding missing columns=%s",
        sorted(missing_columns),
    )
    with engine.begin() as connection:
        for name, definition in missing_columns.items():
            connection.execute(text(f"ALTER TABLE generation_history ADD COLUMN {name} {definition}"))


def ensure_lesson_workflow_compat_columns() -> None:
    """Patch stale local/dev lesson workflow tables when AUTO_CREATE_TABLES is enabled.

    This keeps existing SQLite databases usable after incremental lesson-workflow
    slices add columns. Production should still run Alembic migrations instead of
    depending on startup compatibility patches.
    """
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    pending_columns: dict[str, dict[str, str]] = {}

    for table_name, expected_columns in LESSON_WORKFLOW_COMPAT_TABLE_COLUMNS.items():
        if table_name not in table_names:
            continue
        existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
        missing_columns = {
            name: definition
            for name, definition in expected_columns.items()
            if name not in existing_columns
        }
        if missing_columns:
            pending_columns[table_name] = missing_columns

    if pending_columns:
        logger.warning(
            "database auto-create found stale lesson workflow schema; adding missing columns=%s",
            {table: sorted(columns) for table, columns in pending_columns.items()},
        )
        with engine.begin() as connection:
            for table_name, missing_columns in pending_columns.items():
                for name, definition in missing_columns.items():
                    connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {name} {definition}"))

    refreshed_inspector = inspect(engine)
    with engine.begin() as connection:
        for table_name, index_columns in LESSON_WORKFLOW_COMPAT_INDEXES.items():
            if table_name not in table_names:
                continue
            existing_columns = {column["name"] for column in refreshed_inspector.get_columns(table_name)}
            existing_indexes = {index["name"] for index in refreshed_inspector.get_indexes(table_name)}
            for index_name, column_name in index_columns.items():
                if column_name in existing_columns and index_name not in existing_indexes:
                    connection.execute(text(f"CREATE INDEX {index_name} ON {table_name} ({column_name})"))


def initialize_database() -> None:
    """Create tables for local/dev installs when migrations are not being run explicitly."""
    if not settings.AUTO_CREATE_TABLES:
        logger.info("database auto-create skipped; run Alembic migrations before serving traffic")
        return
    Base.metadata.create_all(bind=engine)
    ensure_generation_history_compat_columns()
    ensure_lesson_workflow_compat_columns()


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Backend API for Latexed - Online LaTeX Editor",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_origin_regex=settings.CORS_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Trusted hosts (production)
if not settings.DEBUG:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.ALLOWED_HOSTS)


# Request correlation, timing and access logging middleware
@app.middleware("http")
async def add_request_logging(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    token = set_request_id(request_id)
    request.state.request_id = request_id
    start_time = time.perf_counter()
    client_host = request.client.host if request.client else "unknown"

    logger.info(
        "request started method=%s path=%s client=%s query=%s user_agent=%s",
        request.method,
        request.url.path,
        client_host,
        request.url.query or "-",
        request.headers.get("User-Agent", "-"),
    )

    try:
        response = await call_next(request)
    except Exception:
        process_time_ms = (time.perf_counter() - start_time) * 1000
        logger.exception(
            "request failed method=%s path=%s client=%s duration_ms=%.2f",
            request.method,
            request.url.path,
            client_host,
            process_time_ms,
        )
        reset_request_id(token)
        raise

    process_time_ms = (time.perf_counter() - start_time) * 1000
    response.headers["X-Process-Time"] = f"{process_time_ms / 1000:.6f}"
    response.headers["X-Request-ID"] = request_id

    log_method = logger.warning if response.status_code >= 400 or process_time_ms >= settings.LOG_SLOW_REQUEST_MS else logger.info
    log_method(
        "request completed method=%s path=%s status=%s duration_ms=%.2f client=%s",
        request.method,
        request.url.path,
        response.status_code,
        process_time_ms,
        client_host,
    )
    reset_request_id(token)
    return response


# Exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("unhandled exception path=%s error=%s", request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )


# Routers
app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
app.include_router(pupils.router, prefix="/api/pupils", tags=["pupils"])
app.include_router(lessons.router, prefix="/api/lessons", tags=["lessons"])
app.include_router(files.router, prefix="/api/files", tags=["files"])
app.include_router(compile.router, prefix="/api/compile", tags=["compile"])
app.include_router(export.router, prefix="/api/export", tags=["export"])
app.include_router(templates.router, prefix="/api/templates", tags=["templates"])
app.include_router(generation.router, prefix="/api/generation", tags=["generation"])


# Health check
@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "version": settings.APP_VERSION,
        "compiler": settings.LATEX_COMPILER,
    }


@app.get("/api/ready", response_model=ReadinessResponse)
async def readiness_check():
    return readiness.build_readiness_response(engine)


@app.get("/")
async def root():
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/api/docs",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        workers=1 if settings.DEBUG else 4,
    )
