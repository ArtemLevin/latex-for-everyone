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
    AUTO_CREATE_TABLES: bool = True

    # LaTeX Compiler
    LATEX_COMPILER: str = "pdflatex"
    COMPILE_TIMEOUT: int = 30
    MAX_FILE_SIZE: int = 100 * 1024 * 1024  # 100MB
    COMPILE_WORK_DIR: str = "/tmp/latexed_compiles"
    MAX_LATEX_FILES: int = 100
    MAX_LATEX_FILE_CHARS: int = 500_000
    MAX_LATEX_TOTAL_CHARS: int = 2_000_000
    MAX_COMPILER_OUTPUT_CHARS: int = 20_000
    LATEX_ALLOWED_EXTENSIONS: str = ".tex,.bib,.cls,.sty"
    ARTIFACT_TTL_SECONDS: int = 24 * 60 * 60

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
    MAX_UPLOAD_SIZE: int = 1000 * 1024 * 1024  # 1000MB

    # Lesson audio/storage foundation
    LESSON_ARTIFACT_ROOT: Optional[str] = None
    MAX_LESSON_AUDIO_SIZE: int = 1000 * 1024 * 1024   # 1000MB
    LESSON_AUDIO_ALLOWED_CONTENT_TYPES: str = "audio/webm,audio/wav,audio/mpeg,audio/mp4,audio/ogg,audio/x-m4a"
    LESSON_AUDIO_ALLOWED_EXTENSIONS: str = ".webm,.wav,.mp3,.m4a,.ogg"
    LESSON_AUDIO_DURATION_PROBE_ENABLED: bool = True
    MAX_LESSON_AUDIO_DURATION_SECONDS: int = 0  # 0 disables duration rejection

    # Lesson transcription foundation
    TRANSCRIPTION_PROVIDER: str = "disabled"
    TRANSCRIPTION_LANGUAGE: str = "ru"
    TRANSCRIPTION_MODEL: str = "small"
    TRANSCRIPTION_BEAM_SIZE: int = 5
    TRANSCRIPTION_DEVICE: str = "cpu"
    TRANSCRIPTION_COMPUTE_TYPE: str = "int8"
    TRANSCRIPTION_WORD_TIMESTAMPS: bool = False

    # Lesson job execution foundation
    LESSON_JOB_EXECUTION_MODE: str = "inline"  # inline or background

    # Lesson document generation foundation
    LESSON_DOCUMENT_PROVIDER: str = "fake"
    LESSON_DOCUMENT_ALLOWED_TYPES: str = "check_list,pupil_mistakes"

    # AI Generation
    AI_PROVIDER: str = "ollama"
    AI_GENERATION_TIMEOUT: int = 120_000
    AI_PROVIDER_STATUS_TIMEOUT: int = 10
    AI_RATE_LIMIT_PER_MINUTE: int = 20
    AI_MAX_MATERIALS_CHARS: int = 20_000
    AI_MAX_PROMPT_CHARS: int = 200_000
    AI_MAX_RAW_OUTPUT_CHARS: int = 200_000
    AI_EXPOSE_PROVIDER_ERRORS: bool = False
    AI_COMPILE_CHECK_ENABLED: bool = True
    AI_REPAIR_ATTEMPTS: int = 1
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5:3b"
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
