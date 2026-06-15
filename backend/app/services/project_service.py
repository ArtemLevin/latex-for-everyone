from collections.abc import Callable
from sqlalchemy.orm import Session

from app.models import File, Project, ProjectSnapshot
from app.schemas import ProjectCreate, ProjectUpdate, SnapshotCreate
from app.time_utils import utc_now


class ProjectServiceError(Exception):
    """Base error for project service operations."""


class SnapshotNotFoundError(ProjectServiceError):
    """Raised when a snapshot does not exist for the requested project."""


class SnapshotProjectMismatchError(ProjectServiceError):
    """Raised when a snapshot request body points to a different project."""


TemplateResolver = Callable[[str], dict[str, str] | None]


class ProjectService:
    """Business rules for project, snapshot and duplication workflows."""

    def list_projects(self, db: Session, *, owner_id: str, skip: int, limit: int, search: str | None = None) -> list[Project]:
        query = db.query(Project).filter(Project.owner_id == owner_id)
        if search:
            query = query.filter(Project.name.ilike(f"%{search}%"))
        return query.order_by(Project.updated_at.desc()).offset(skip).limit(limit).all()

    def create_project(
        self,
        db: Session,
        project_data: ProjectCreate,
        *,
        owner_id: str,
        template_resolver: TemplateResolver | None = None,
    ) -> Project:
        project = Project(
            name=project_data.name,
            owner_id=owner_id,
            is_public=project_data.is_public,
        )
        db.add(project)
        db.flush()

        main_content = ""
        if project_data.template and template_resolver:
            template = template_resolver(project_data.template)
            if template:
                main_content = template["content"]

        db.add(
            File(
                project_id=project.id,
                name="main.tex",
                content=main_content,
                is_main=True,
            )
        )
        db.commit()
        db.refresh(project)
        return project

    def update_project(self, db: Session, project: Project, project_data: ProjectUpdate) -> Project:
        update_data = project_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(project, key, value)

        project.updated_at = utc_now()
        db.commit()
        db.refresh(project)
        return project

    def delete_project(self, db: Session, project: Project) -> str:
        project_name = project.name
        db.delete(project)
        db.commit()
        return project_name

    def create_snapshot(self, db: Session, project: Project, snapshot_data: SnapshotCreate) -> ProjectSnapshot:
        if snapshot_data.project_id and snapshot_data.project_id != project.id:
            raise SnapshotProjectMismatchError("Snapshot project_id does not match path project_id")

        snapshot = ProjectSnapshot(
            project_id=project.id,
            name=snapshot_data.name,
            data=snapshot_data.data,
        )
        db.add(snapshot)
        db.commit()
        db.refresh(snapshot)
        return snapshot

    def list_snapshots(self, db: Session, project: Project) -> list[ProjectSnapshot]:
        return (
            db.query(ProjectSnapshot)
            .filter(ProjectSnapshot.project_id == project.id)
            .order_by(ProjectSnapshot.created_at.desc())
            .limit(50)
            .all()
        )

    def restore_snapshot(self, db: Session, project: Project, snapshot_id: str) -> None:
        snapshot = (
            db.query(ProjectSnapshot)
            .filter(
                ProjectSnapshot.id == snapshot_id,
                ProjectSnapshot.project_id == project.id,
            )
            .first()
        )
        if not snapshot:
            raise SnapshotNotFoundError("Snapshot not found")

        files_data = snapshot.data.get("files", [])
        db.query(File).filter(File.project_id == project.id).delete()
        for file_data in files_data:
            db.add(
                File(
                    project_id=project.id,
                    name=file_data["name"],
                    content=file_data["content"],
                    is_main=file_data.get("is_main", False),
                )
            )

        project.updated_at = utc_now()
        db.commit()

    def duplicate_project(self, db: Session, project: Project, *, owner_id: str) -> Project:
        new_project = Project(
            name=f"{project.name} (копия)",
            owner_id=owner_id,
            is_public=False,
        )
        db.add(new_project)
        db.flush()

        for file in project.files:
            db.add(
                File(
                    project_id=new_project.id,
                    name=file.name,
                    content=file.content,
                    is_main=file.is_main,
                )
            )

        db.commit()
        db.refresh(new_project)
        return new_project
