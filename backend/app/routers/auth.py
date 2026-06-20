import time

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models import AuthSession, User
from app.schemas import AuthTokenResponse, LoginRequest, LogoutResponse, RefreshRequest, RegisterRequest, UserPublic
from app.services.auth_audit import AuthAuditService
from app.services.auth_tokens import AccessTokenError, decode_access_token, hash_refresh_token
from app.services.auth_passwords import PasswordValidationError, hash_password, verify_password
from app.services.auth_sessions import AuthSessionError, AuthSessionService
from app.services.users import UserService, normalize_email

router = APIRouter()
user_service = UserService()
audit_service = AuthAuditService()
session_service = AuthSessionService(audit_service=audit_service)
_login_buckets: dict[str, list[float]] = {}


def _user_public(user: User) -> UserPublic:
    return UserPublic(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        auth_provider=user.auth_provider,
    )


def _set_auth_cookies(response: Response, *, access_token: str, refresh_token: str) -> None:
    if not settings.AUTH_COOKIE_MODE:
        return
    response.set_cookie(
        settings.AUTH_ACCESS_COOKIE_NAME,
        access_token,
        httponly=True,
        secure=settings.AUTH_COOKIE_SECURE,
        samesite=settings.AUTH_COOKIE_SAMESITE,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )
    response.set_cookie(
        settings.AUTH_REFRESH_COOKIE_NAME,
        refresh_token,
        httponly=True,
        secure=settings.AUTH_COOKIE_SECURE,
        samesite=settings.AUTH_COOKIE_SAMESITE,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        path="/api/auth",
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(settings.AUTH_ACCESS_COOKIE_NAME, path="/")
    response.delete_cookie(settings.AUTH_REFRESH_COOKIE_NAME, path="/api/auth")


def _rate_limit_login(request: Request, email: str) -> None:
    limit = settings.AUTH_LOGIN_RATE_LIMIT_PER_MINUTE
    if limit <= 0:
        return
    key = f"{request.client.host if request.client else 'unknown'}:{normalize_email(email)}"
    now = time.monotonic()
    window_start = now - 60
    bucket = [item for item in _login_buckets.get(key, []) if item >= window_start]
    if len(bucket) >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts",
            headers={"Retry-After": "60"},
        )
    bucket.append(now)
    _login_buckets[key] = bucket


def _refresh_token_from_request(request: Request, body: RefreshRequest) -> str | None:
    return body.refresh_token or request.cookies.get(settings.AUTH_REFRESH_COOKIE_NAME)


def _access_session_id_from_request(request: Request) -> str | None:
    authorization = request.headers.get("Authorization")
    token = None
    if authorization:
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() == "bearer":
            token = value.strip()
    token = token or request.cookies.get(settings.AUTH_ACCESS_COOKIE_NAME)
    if not token:
        return None
    try:
        return decode_access_token(token).get("sid")
    except AccessTokenError:
        return None


@router.post("/login", response_model=AuthTokenResponse)
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    _rate_limit_login(request, payload.email)
    user = user_service.get_by_email(db, payload.email)
    if not user or user.auth_provider != "password" or not user.password_hash:
        audit_service.record(
            db, event_type="login_failed", request=request, metadata={"email": normalize_email(payload.email)}
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    if not user.is_active:
        audit_service.record(db, event_type="user_disabled", user_id=user.id, request=request)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User disabled")
    if not verify_password(payload.password, user.password_hash):
        audit_service.record(db, event_type="login_failed", user_id=user.id, request=request)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    issued = session_service.create_session(db, user=user, request=request)
    audit_service.record(db, event_type="login_success", user_id=user.id, session_id=issued.session.id, request=request)
    _set_auth_cookies(response, access_token=issued.access_token, refresh_token=issued.refresh_token)
    return AuthTokenResponse(
        access_token=issued.access_token,
        expires_in=issued.expires_in,
        user=_user_public(user),
    )


@router.post("/refresh", response_model=AuthTokenResponse)
def refresh(
    payload: RefreshRequest = Body(default_factory=RefreshRequest),
    request: Request = None,
    response: Response = None,
    db: Session = Depends(get_db),
):
    refresh_token = _refresh_token_from_request(request, payload)
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token is required")
    try:
        issued = session_service.refresh(db, refresh_token=refresh_token, request=request)
    except AuthSessionError as exc:
        _clear_auth_cookies(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    _set_auth_cookies(response, access_token=issued.access_token, refresh_token=issued.refresh_token)
    return AuthTokenResponse(
        access_token=issued.access_token, expires_in=issued.expires_in, user=_user_public(issued.session.user)
    )


@router.post("/logout", response_model=LogoutResponse)
def logout(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = None
    access_session_id = _access_session_id_from_request(request)
    if access_session_id:
        session = (
            db.query(AuthSession)
            .filter(AuthSession.id == access_session_id, AuthSession.user_id == current_user.id)
            .first()
        )
    refresh_token = request.cookies.get(settings.AUTH_REFRESH_COOKIE_NAME)
    if session is None and refresh_token:
        session = (
            db.query(AuthSession).filter(AuthSession.refresh_token_hash == hash_refresh_token(refresh_token)).first()
        )
    if session is None:
        session = (
            db.query(AuthSession).filter(AuthSession.user_id == current_user.id, AuthSession.status == "active").first()
        )
    revoked = 0
    if session:
        session_service.revoke_session(db, session=session, reason="logout")
        audit_service.record(db, event_type="logout", user_id=current_user.id, session_id=session.id, request=request)
        revoked = 1
    _clear_auth_cookies(response)
    return LogoutResponse(revoked_sessions=revoked)


@router.post("/logout-all", response_model=LogoutResponse)
def logout_all(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    revoked = session_service.revoke_all_user_sessions(db, user_id=current_user.id, reason="logout_all")
    audit_service.record(
        db, event_type="logout_all", user_id=current_user.id, request=request, metadata={"count": revoked}
    )
    _clear_auth_cookies(response)
    return LogoutResponse(revoked_sessions=revoked)


@router.get("/me", response_model=UserPublic)
def me(current_user: User = Depends(get_current_user)):
    return _user_public(current_user)


@router.post("/register", response_model=AuthTokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    if not settings.AUTH_REGISTRATION_ENABLED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Registration is disabled")
    if user_service.get_by_email(db, payload.email):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    try:
        password_hash = hash_password(payload.password)
    except PasswordValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    user = user_service.create_user(
        db,
        email=payload.email,
        display_name=payload.display_name,
        password_hash=password_hash,
        auth_provider="password",
        is_verified=False,
    )
    issued = session_service.create_session(db, user=user, request=request)
    audit_service.record(db, event_type="login_success", user_id=user.id, session_id=issued.session.id, request=request)
    _set_auth_cookies(response, access_token=issued.access_token, refresh_token=issued.refresh_token)
    return AuthTokenResponse(access_token=issued.access_token, expires_in=issued.expires_in, user=_user_public(user))
