from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from app.config import settings
from app.database import engine, Base
from app.logging_config import configure_logging, reset_request_id, set_request_id
from app.routers import files, compile, export, templates, projects, generation
import logging
import time
import uuid

# Create tables
Base.metadata.create_all(bind=engine)

# Logging
configure_logging()
logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Backend API for Latexed - Online LaTeX Editor",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Trusted hosts (production)
if not settings.DEBUG:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])


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
