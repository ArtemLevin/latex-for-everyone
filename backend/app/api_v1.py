"""
API v1 router that combines all sub-routers.
Use this for versioned API: /api/v1/...
"""
from fastapi import APIRouter
from app.routers import files, compile, export, templates, projects, pupils, lessons

api_v1_router = APIRouter()

api_v1_router.include_router(projects.router, prefix="/projects", tags=["projects"])
api_v1_router.include_router(pupils.router, prefix="/pupils", tags=["pupils"])
api_v1_router.include_router(lessons.router, prefix="/lessons", tags=["lessons"])
api_v1_router.include_router(files.router, prefix="/files", tags=["files"])
api_v1_router.include_router(compile.router, prefix="/compile", tags=["compile"])
api_v1_router.include_router(export.router, prefix="/export", tags=["export"])
api_v1_router.include_router(templates.router, prefix="/templates", tags=["templates"])
