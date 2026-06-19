from sqlalchemy.orm import Session

from app.config import settings
from app.models import File, Project
from app.schemas import FileCreate, FileUpdate
from app.services.latex_file_policy import LatexFilePolicyError, parse_allowed_extensions, validate_latex_filename
from app.services.project_file_validation import validate_project_latex_files
from app.time_utils import utc_now


class FileServiceError(Exception):
    """Base error for file service operations."""


class FileNotFoundError(FileServiceError):
    """Raised when a file row cannot be found."""


class FileConflictError(FileServiceError):
    """Raised when a file operation would violate a project invariant."""


class InvalidFileNameError(FileServiceError):
    """Raised when a project file name is unsafe or unsupported."""


def _safe_file_name(name: str | None) -> str:
    try:
        return validate_latex_filename(
            name or "",
            allowed_extensions=parse_allowed_extensions(settings.LATEX_ALLOWED_EXTENSIONS),
        )
    except LatexFilePolicyError as exc:
        raise InvalidFileNameError(str(exc)) from exc


def _project_file_map(project: Project) -> dict[str, str]:
    return {file.name: file.content for file in project.files}


class FileService:
    """Business rules for project file CRUD and upload workflows."""

    def list_project_files(self, db: Session, project_id: str) -> list[File]:
        return (
            db.query(File)
            .filter(File.project_id == project_id)
            .order_by(File.is_main.desc(), File.name)
            .all()
        )

    def create_file(self, db: Session, project: Project, file_data: FileCreate) -> File:
        file_name = _safe_file_name(file_data.name)
        self._ensure_unique_name(db, project.id, file_name)
        future_files = _project_file_map(project)
        future_files[file_name] = file_data.content
        validate_project_latex_files(future_files)

        if file_data.is_main:
            self._unset_other_main_files(db, project.id)

        new_file = File(
            project_id=project.id,
            name=file_name,
            content=file_data.content,
            is_main=file_data.is_main,
        )
        db.add(new_file)
        db.commit()
        db.refresh(new_file)
        return new_file

    def get_file(self, db: Session, file_id: str, *, owner_id: str | None = None) -> File:
        query = db.query(File).filter(File.id == file_id)
        if owner_id is not None:
            query = query.join(Project).filter(Project.owner_id == owner_id)
        file = query.first()
        if not file:
            raise FileNotFoundError("File not found")
        return file

    def update_file(self, db: Session, file_id: str, file_data: FileUpdate, *, owner_id: str | None = None) -> File:
        file = self.get_file(db, file_id, owner_id=owner_id)
        update_data = file_data.model_dump(exclude_unset=True)

        if "name" in update_data:
            update_data["name"] = _safe_file_name(update_data["name"])
            self._ensure_unique_name(db, file.project_id, update_data["name"], exclude_file_id=file_id)

        future_name = update_data.get("name", file.name)
        future_content = update_data.get("content", file.content)
        future_files = {
            existing.name: existing.content
            for existing in file.project.files
            if existing.id != file.id
        }
        future_files[future_name] = future_content
        validate_project_latex_files(future_files)

        if update_data.get("is_main"):
            self._unset_other_main_files(db, file.project_id, exclude_file_id=file_id)

        for key, value in update_data.items():
            setattr(file, key, value)

        file.updated_at = utc_now()
        db.commit()
        db.refresh(file)
        return file

    def delete_file(self, db: Session, file_id: str, *, owner_id: str | None = None) -> str:
        file = self.get_file(db, file_id, owner_id=owner_id)
        file_count = db.query(File).filter(File.project_id == file.project_id).count()
        if file_count <= 1:
            raise FileConflictError("Cannot delete the last file in project")

        file_name = file.name
        db.delete(file)
        db.commit()
        return file_name

    def replace_file_content(self, db: Session, file_id: str, content: str, *, owner_id: str | None = None) -> None:
        file = self.get_file(db, file_id, owner_id=owner_id)
        future_files = _project_file_map(file.project)
        future_files[file.name] = content
        validate_project_latex_files(future_files)

        file.content = content
        file.updated_at = utc_now()
        db.commit()

    def upload_project_files(self, db: Session, project: Project, uploads: list[tuple[str | None, str]]) -> int:
        normalized_uploads = [(_safe_file_name(upload_name), content) for upload_name, content in uploads]
        future_files = _project_file_map(project)
        for file_name, content in normalized_uploads:
            future_files[file_name] = content
        validate_project_latex_files(future_files)

        for file_name, content in normalized_uploads:
            existing = (
                db.query(File)
                .filter(File.project_id == project.id, File.name == file_name)
                .first()
            )

            if existing:
                existing.content = content
                existing.updated_at = utc_now()
            else:
                db.add(
                    File(
                        project_id=project.id,
                        name=file_name,
                        content=content,
                    )
                )

        db.commit()
        return len(uploads)

    def _ensure_unique_name(
        self,
        db: Session,
        project_id: str,
        name: str,
        *,
        exclude_file_id: str | None = None,
    ) -> None:
        query = db.query(File).filter(File.project_id == project_id, File.name == name)
        if exclude_file_id:
            query = query.filter(File.id != exclude_file_id)
        if query.first():
            raise FileConflictError(f"File '{name}' already exists")

    def _unset_other_main_files(self, db: Session, project_id: str, *, exclude_file_id: str | None = None) -> None:
        query = db.query(File).filter(File.project_id == project_id, File.is_main == True)
        if exclude_file_id:
            query = query.filter(File.id != exclude_file_id)
        query.update({"is_main": False})
