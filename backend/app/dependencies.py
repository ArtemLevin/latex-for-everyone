import ipaddress
import uuid

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import AuthSession, Project, User
from app.services.auth_audit import AuthAuditService
from app.services.auth_sessions import AuthSessionService
from app.services.auth_tokens import AccessTokenError, decode_access_token
from app.services.users import UserService


DEFAULT_TEACHER_ID = "local-teacher"
SUPPORTED_AUTH_MODES = {"local", "password", "trusted_proxy"}
user_service = UserService()
audit_service = AuthAuditService()
auth_session_service = AuthSessionService(audit_service=audit_service)


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
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Trusted proxy auth is not configured"
        )
    if not _is_trusted_proxy_request(request):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Trusted proxy identity is not allowed from this client",
        )

    header_value = request.headers.get(settings.TRUSTED_USER_HEADER)
    if header_value is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Trusted proxy identity header is required"
        )
    return _normalize_identity(header_value)


def _resolve_bearer_token(request: Request) -> str | None:
    authorization = request.headers.get("Authorization")
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer" and token:
            return token.strip()
    cookie_token = request.cookies.get(settings.AUTH_ACCESS_COOKIE_NAME)
    return cookie_token or None


def _require_active_user(user: User | None) -> User:
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User disabled")
    return user


def _resolve_local_user(request: Request, db: Session) -> User:
    user = _require_active_user(user_service.ensure_local_user(db, identity=_resolve_local_identity()))
    audit_service.record(db, event_type="local_login", user_id=user.id, request=request)
    return user


def _resolve_trusted_proxy_user(request: Request, db: Session) -> User:
    identity = _resolve_trusted_proxy_identity(request)
    user = user_service.get_by_provider_subject(db, provider="trusted_proxy", subject=identity)
    if user is None:
        if not settings.TRUSTED_PROXY_AUTO_PROVISION_USERS:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Trusted proxy user is not provisioned")
        user = user_service.ensure_trusted_proxy_user(db, identity=identity, role=settings.TRUSTED_PROXY_DEFAULT_ROLE)
        audit_service.record(db, event_type="trusted_proxy_user_created", user_id=user.id, request=request)
    audit_service.record(db, event_type="trusted_proxy_login", user_id=user.id, request=request)
    return _require_active_user(user)


def _resolve_password_user(request: Request, db: Session) -> User:
    token = _resolve_bearer_token(request)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        claims = decode_access_token(token)
    except AccessTokenError as exc:
        audit_service.record(db, event_type="access_token_invalid", request=request)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc
    session = auth_session_service.get_active_session(db, session_id=claims["sid"])
    if not session:
        audit_service.record(db, event_type="access_token_invalid", user_id=claims.get("sub"), request=request)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user = user_service.get_by_id(db, claims["sub"])
    if not user or user.id != session.user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return _require_active_user(user)


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Resolve the current authenticated user for local, password, and trusted-proxy modes."""
    mode = _normalize_auth_mode()
    if mode == "local":
        return _resolve_local_user(request, db)
    if mode == "trusted_proxy":
        return _resolve_trusted_proxy_user(request, db)
    return _resolve_password_user(request, db)


def get_current_user_id(user: User = Depends(get_current_user)) -> str:
    """Compatibility wrapper for existing owner_id/teacher_id scoped routers."""
    return user.id


def get_project(
    project_id: str,
    db: Session = Depends(get_db),
    owner_id: str = Depends(get_current_user_id),
) -> Project:
    try:
        uuid.UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid project ID format")

    project = db.query(Project).filter(Project.id == project_id, Project.owner_id == owner_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Project {project_id} not found")
    return project


def get_project_files(
    project_id: str,
    db: Session = Depends(get_db),
    owner_id: str = Depends(get_current_user_id),
) -> list:
    from app.models import File

    return db.query(File).join(Project).filter(File.project_id == project_id, Project.owner_id == owner_id).all()


def get_current_teacher_id(user_id: str = Depends(get_current_user_id)) -> str:
    """Use the authenticated user id for lesson teacher scoping and project ownership."""
    return user_id
