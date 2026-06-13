import uuid
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Boolean, Integer, JSON, Float
from sqlalchemy.orm import relationship
from app.database import Base
from app.time_utils import utc_now


class Project(Base):
    __tablename__ = "projects"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False, default="Безымянный проект")
    owner_id = Column(String(255), nullable=True, index=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)
    is_public = Column(Boolean, default=False)
    settings = Column(JSON, default=lambda: {"theme": "monokai", "fontSize": 14, "autoCompile": False})

    files = relationship("File", back_populates="project", cascade="all, delete-orphan")
    compile_history = relationship("CompileHistory", back_populates="project", cascade="all, delete-orphan")
    snapshots = relationship("ProjectSnapshot", back_populates="project", cascade="all, delete-orphan")
    generation_history = relationship("GenerationHistory", back_populates="project", cascade="all, delete-orphan")


class Pupil(Base):
    __tablename__ = "pupils"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    teacher_id = Column(String(255), nullable=False, index=True)
    display_name = Column(String(255), nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    lessons = relationship("Lesson", back_populates="pupil", cascade="all, delete-orphan")


class Lesson(Base):
    __tablename__ = "lessons"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    pupil_id = Column(String(36), ForeignKey("pupils.id"), nullable=False, index=True)
    teacher_id = Column(String(255), nullable=False, index=True)
    topic = Column(String(255), nullable=False)
    lesson_date = Column(DateTime, nullable=False, default=utc_now, index=True)
    status = Column(String(50), nullable=False, default="draft")
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    pupil = relationship("Pupil", back_populates="lessons")
    recordings = relationship("LessonAudioRecording", back_populates="lesson", cascade="all, delete-orphan")
    transcripts = relationship("LessonTranscript", back_populates="lesson", cascade="all, delete-orphan")
    generated_documents = relationship("LessonGeneratedDocument", back_populates="lesson", cascade="all, delete-orphan")
    processing_jobs = relationship("LessonProcessingJob", back_populates="lesson", cascade="all, delete-orphan")


class LessonAudioRecording(Base):
    __tablename__ = "lesson_audio_recordings"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    lesson_id = Column(String(36), ForeignKey("lessons.id"), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    content_type = Column(String(100), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    duration_seconds = Column(Float, nullable=True)
    sha256_checksum = Column(String(64), nullable=True)
    storage_path = Column(Text, nullable=False)
    status = Column(String(50), nullable=False, default="uploaded")
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    lesson = relationship("Lesson", back_populates="recordings")
    transcripts = relationship("LessonTranscript", back_populates="recording", cascade="all, delete-orphan")


class LessonTranscript(Base):
    __tablename__ = "lesson_transcripts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    lesson_id = Column(String(36), ForeignKey("lessons.id"), nullable=False, index=True)
    recording_id = Column(String(36), ForeignKey("lesson_audio_recordings.id"), nullable=False, index=True)
    provider = Column(String(100), nullable=False)
    language = Column(String(20), nullable=False)
    text = Column(Text, nullable=True)
    status = Column(String(50), nullable=False, default="completed")
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    lesson = relationship("Lesson", back_populates="transcripts")
    recording = relationship("LessonAudioRecording", back_populates="transcripts")
    generated_documents = relationship("LessonGeneratedDocument", back_populates="transcript", cascade="all, delete-orphan")


class LessonGeneratedDocument(Base):
    __tablename__ = "lesson_generated_documents"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    lesson_id = Column(String(36), ForeignKey("lessons.id"), nullable=False, index=True)
    transcript_id = Column(String(36), ForeignKey("lesson_transcripts.id"), nullable=False, index=True)
    document_type = Column(String(50), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    filename = Column(String(255), nullable=False)
    content_type = Column(String(100), nullable=False, default="application/x-tex")
    storage_path = Column(Text, nullable=False)
    status = Column(String(50), nullable=False, default="completed")
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    lesson = relationship("Lesson", back_populates="generated_documents")
    transcript = relationship("LessonTranscript", back_populates="generated_documents")


class LessonProcessingJob(Base):
    __tablename__ = "lesson_processing_jobs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    lesson_id = Column(String(36), ForeignKey("lessons.id"), nullable=False, index=True)
    teacher_id = Column(String(255), nullable=False, index=True)
    job_type = Column(String(50), nullable=False, index=True)
    status = Column(String(50), nullable=False, default="queued", index=True)
    stage = Column(String(50), nullable=False, default="queued")
    recording_id = Column(String(36), nullable=True)
    transcript_id = Column(String(36), nullable=True)
    document_types = Column(JSON, nullable=False, default=list)
    document_ids = Column(JSON, nullable=False, default=list)
    error_message = Column(Text, nullable=True)
    attempts = Column(Integer, nullable=False, default=0)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    lesson = relationship("Lesson", back_populates="processing_jobs")


class File(Base):
    __tablename__ = "files"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)
    name = Column(String(255), nullable=False)
    content = Column(Text, default="")
    is_main = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    project = relationship("Project", back_populates="files")


class CompileHistory(Base):
    __tablename__ = "compile_history"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)
    status = Column(String(50), default="pending")  # pending, success, error
    output = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    compile_time = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=utc_now)

    project = relationship("Project", back_populates="compile_history")


class ProjectSnapshot(Base):
    __tablename__ = "project_snapshots"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)
    name = Column(String(255), default="Автосохранение")
    data = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=utc_now)

    project = relationship("Project", back_populates="snapshots")


class GenerationHistory(Base):
    __tablename__ = "generation_history"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True, index=True)
    provider = Column(String(100), nullable=False)
    model = Column(String(255), nullable=True)
    status = Column(String(50), nullable=False, default="success")
    prompt_hash = Column(String(64), nullable=False)
    prompt_preview = Column(Text, nullable=True)
    raw_output_hash = Column(String(64), nullable=True)
    latex_code_hash = Column(String(64), nullable=True)
    latex_code_preview = Column(Text, nullable=True)
    fields = Column(JSON, nullable=False)
    validation = Column(JSON, nullable=True)
    compile_check = Column(JSON, nullable=True)
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    total_tokens = Column(Integer, nullable=True)
    token_count_source = Column(String(50), nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now)

    project = relationship("Project", back_populates="generation_history")
