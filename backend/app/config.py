import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    APP_NAME: str = "Latexed API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = "sqlite:///./latexed.db"
    DB_POOL_SIZE: int = 5

    # LaTeX Compiler
    LATEX_COMPILER: str = "pdflatex"
    COMPILE_TIMEOUT: int = 30
    MAX_FILE_SIZE: int = 10 * 1024 * 1024  # 10MB
    COMPILE_WORK_DIR: str = "/tmp/latexed_compiles"
    MAX_LATEX_FILES: int = 100
    MAX_LATEX_FILE_CHARS: int = 500_000
    MAX_LATEX_TOTAL_CHARS: int = 2_000_000

    # Security
    SECRET_KEY: str = "change-me-in-production-please"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    # Keep local defaults permissive for development/TestClient; production deployments
    # should override this with the exact reverse-proxy and public hostnames.
    ALLOWED_HOSTS: list[str] = ["*"]

    # CORS
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:8080",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8080",
        "http://0.0.0.0:3000",
        "http://0.0.0.0:8080",
    ]
    CORS_ORIGIN_REGEX: Optional[str] = r"^https?://(localhost|127\.0\.0\.1|0\.0\.0\.0)(:\d+)?$"

    # Upload
    UPLOAD_DIR: str = "/tmp/latexed_uploads"
    MAX_UPLOAD_SIZE: int = 50 * 1024 * 1024  # 50MB

    # AI Generation
    AI_PROVIDER: str = "ollama"
    AI_GENERATION_TIMEOUT: int = 120_000
    AI_PROVIDER_STATUS_TIMEOUT: int = 10
    AI_RATE_LIMIT_PER_MINUTE: int = 20
    AI_MAX_MATERIALS_CHARS: int = 20_000
    AI_MAX_PROMPT_CHARS: int = 60_000_000
    AI_MAX_RAW_OUTPUT_CHARS: int = 200_000_000
    AI_EXPOSE_PROVIDER_ERRORS: bool = False
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "gemma4"
    AI_VENDOR_BASE_URL: str = "https://api.openai.com/v1"
    AI_VENDOR_API_KEY: Optional[str] = None
    AI_VENDOR_MODEL: str = "gpt-4o-mini"
    AI_VENDOR_TEMPERATURE: float = 0.2

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "%(asctime)s %(levelname)s [%(name)s] [request_id=%(request_id)s] %(message)s"
    LOG_SLOW_REQUEST_MS: int = 1000
    AI_LOG_PROMPT_PREVIEW_CHARS: int = 500

    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 60
    COMPILE_RATE_LIMIT_PER_HOUR: int = 100


settings = Settings()

# Ensure directories exist
Path(settings.COMPILE_WORK_DIR).mkdir(parents=True, exist_ok=True)
Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
