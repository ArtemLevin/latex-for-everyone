import ipaddress
import uuid

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Project


DEFAULT_TEACHER_ID = "local-teacher"
SUPPORTED_AUTH_MODES = {"local", "trusted_proxy"}


def _normalize_identity(value: str) -> str:
    identity = value.strip()
    if not identity or len(identity) > 255 or any(ord(char) < 32 for char in identity):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid user identity")
    return identity


def _normalize_auth_mode() -> str:
    mode = settings.AUTH_MODE.strip().lower()
    if mode not in SUPPORTED_AUTH_MODES:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Invalid auth configuration")
    return mode


def _resolve_local_identity() -> str:
    return _normalize_identity(settings.LOCAL_USER_ID or DEFAULT_TEACHER_ID)


def _request_client_host(request: Request) -> str:
    return request.client.host if request.client else ""


def _trusted_proxy_matches(client_host: str, trusted_proxy: str) -> bool:
    trusted_proxy = trusted_proxy.strip()
    if not trusted_proxy:
        return False
    if client_host == trusted_proxy:
        return True
    try:
        client_ip = ipaddress.ip_address(client_host)
    except ValueError:
        return False
    try:
        if "/" in trusted_proxy:
            return client_ip in ipaddress.ip_network(trusted_proxy, strict=False)
        return client_ip == ipaddress.ip_address(trusted_proxy)
    except ValueError:
        return False


def _is_trusted_proxy_request(request: Request) -> bool:
    client_host = _request_client_host(request)
    return any(_trusted_proxy_matches(client_host, proxy) for proxy in settings.TRUSTED_PROXY_IPS)


def _resolve_trusted_proxy_identity(request: Request) -> str:
    if not settings.TRUSTED_PROXY_IPS:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Trusted proxy auth is not configured")
    if not _is_trusted_proxy_request(request):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Trusted proxy identity is not allowed from this client")

    header_value = request.headers.get(settings.TRUSTED_USER_HEADER)
    if header_value is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Trusted proxy identity header is required")
    return _normalize_identity(header_value)


def get_current_user_id(request: Request) -> str:
    """Resolve identity through an explicit auth mode.

    ``local`` mode intentionally ignores any client-supplied trusted identity
    header. ``trusted_proxy`` mode accepts the configured header only from
    configured trusted proxy addresses.
    """
    mode = _normalize_auth_mode()
    if mode == "local":
        return _resolve_local_identity()
    return _resolve_trusted_proxy_identity(request)


def get_project(
    project_id: str,
    db: Session = Depends(get_db),
    owner_id: str = Depends(get_current_user_id),
) -> Project:
    try:
        uuid.UUID(project_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid project ID format"
        )

    project = db.query(Project).filter(Project.id == project_id, Project.owner_id == owner_id).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found"
        )
    return project


def get_project_files(
    project_id: str,
    db: Session = Depends(get_db),
    owner_id: str = Depends(get_current_user_id),
) -> list:
    from app.models import File

    return db.query(File).join(Project).filter(File.project_id == project_id, Project.owner_id == owner_id).all()


def get_current_teacher_id(user_id: str = Depends(get_current_user_id)) -> str:
    """Use the same MVP identity for lesson teacher scoping and project ownership."""
    return user_id
