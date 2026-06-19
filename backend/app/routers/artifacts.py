from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user_id
from app.services.artifact_service import (
    ArtifactExpiredError,
    ArtifactMissingFileError,
    ArtifactNotFoundError,
    get_authorized_artifact_download,
    mark_artifact_accessed,
)

router = APIRouter()


@router.get("/{artifact_id}/download")
async def download_artifact(
    artifact_id: str,
    owner_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    try:
        download = get_authorized_artifact_download(db, artifact_id=artifact_id, owner_id=owner_id)
    except ArtifactExpiredError as exc:
        db.commit()
        raise HTTPException(status_code=410, detail="Artifact expired") from exc
    except ArtifactMissingFileError as exc:
        db.commit()
        raise HTTPException(status_code=404, detail="Artifact file not found") from exc
    except ArtifactNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Artifact not found") from exc

    mark_artifact_accessed(db, artifact=download.artifact)
    return FileResponse(
        path=str(download.target.path),
        filename=download.artifact.original_filename,
        media_type=download.artifact.media_type,
        content_disposition_type=download.artifact.content_disposition_type,
    )
