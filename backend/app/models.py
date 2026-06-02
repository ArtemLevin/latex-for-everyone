import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Boolean, JSON
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
