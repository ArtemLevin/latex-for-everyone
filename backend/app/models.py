import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Boolean, Integer, JSON
from sqlalchemy.orm import relationship
from app.database import Base


class Project(Base):
    __tablename__ = "projects"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False, default="Безымянный проект")
    owner_id = Column(String(255), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_public = Column(Boolean, default=False)
    settings = Column(JSON, default=lambda: {"theme": "monokai", "fontSize": 14, "autoCompile": False})

    files = relationship("File", back_populates="project", cascade="all, delete-orphan")
    compile_history = relationship("CompileHistory", back_populates="project", cascade="all, delete-orphan")
    snapshots = relationship("ProjectSnapshot", back_populates="project", cascade="all, delete-orphan")
    generation_history = relationship("GenerationHistory", back_populates="project", cascade="all, delete-orphan")


class File(Base):
    __tablename__ = "files"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)
    name = Column(String(255), nullable=False)
    content = Column(Text, default="")
    is_main = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project = relationship("Project", back_populates="files")


class CompileHistory(Base):
    __tablename__ = "compile_history"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)
    status = Column(String(50), default="pending")  # pending, success, error
    output = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    compile_time = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", back_populates="compile_history")


class ProjectSnapshot(Base):
    __tablename__ = "project_snapshots"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)
    name = Column(String(255), default="Автосохранение")
    data = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

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
    created_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", back_populates="generation_history")
