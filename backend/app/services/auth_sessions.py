import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import Request
from sqlalchemy.orm import Session

from app.config import settings
from app.models import AuthSession, User
from app.services.auth_audit import AuthAuditService, hash_for_audit, request_client_host
from app.services.auth_tokens import create_access_token, generate_refresh_token, hash_refresh_token
from app.time_utils import utc_now


class AuthSessionError(ValueError):
    pass


@dataclass(frozen=True)
class IssuedTokens:
    access_token: str
    refresh_token: str
    expires_in: int
    session: AuthSession


def _as_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


class AuthSessionService:
    def __init__(self, audit_service: AuthAuditService | None = None) -> None:
        self.audit_service = audit_service or AuthAuditService()

    def create_session(self, db: Session, *, user: User, request: Request | None = None) -> IssuedTokens:
        refresh_token = generate_refresh_token()
        now = utc_now()
        session = AuthSession(
            user_id=user.id,
            refresh_token_hash=hash_refresh_token(refresh_token),
            refresh_token_family_id=str(uuid.uuid4()),
            user_agent_hash=hash_for_audit(request.headers.get("User-Agent") if request else None),
            ip_address_hash=hash_for_audit(request_client_host(request)),
            status="active",
            created_at=now,
            expires_at=now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        )
        user.last_login_at = now
        user.updated_at = now
        db.add(session)
        db.add(user)
        db.commit()
        db.refresh(session)
        access_token = create_access_token(user, session_id=session.id)
        return IssuedTokens(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            session=session,
        )

    def refresh(self, db: Session, *, refresh_token: str, request: Request | None = None) -> IssuedTokens:
        token_hash = hash_refresh_token(refresh_token)
        session = db.query(AuthSession).filter(AuthSession.refresh_token_hash == token_hash).first()
        now = utc_now()
        if session is None:
            self.audit_service.record(db, event_type="refresh_failed", request=request)
            raise AuthSessionError("Invalid refresh token")
        if session.status == "rotated":
            self.revoke_family(db, family_id=session.refresh_token_family_id, reason="refresh token reuse detected")
            self.audit_service.record(
                db,
                event_type="refresh_reuse_detected",
                user_id=session.user_id,
                session_id=session.id,
                request=request,
            )
            raise AuthSessionError("Invalid refresh token")
        if session.status != "active":
            self.audit_service.record(
                db, event_type="refresh_failed", user_id=session.user_id, session_id=session.id, request=request
            )
            raise AuthSessionError("Invalid refresh token")
        if _as_aware(session.expires_at) < now:
            session.status = "expired"
            session.revoked_at = now
            session.revoke_reason = "refresh token expired"
            db.add(session)
            db.commit()
            self.audit_service.record(
                db, event_type="refresh_failed", user_id=session.user_id, session_id=session.id, request=request
            )
            raise AuthSessionError("Refresh session expired")
        user = session.user
        if not user or not user.is_active:
            raise AuthSessionError("User disabled")

        session.status = "rotated"
        session.last_used_at = now
        session.revoked_at = now
        session.revoke_reason = "refresh token rotated"
        db.add(session)

        refresh_token_new = generate_refresh_token()
        new_session = AuthSession(
            user_id=user.id,
            refresh_token_hash=hash_refresh_token(refresh_token_new),
            refresh_token_family_id=session.refresh_token_family_id,
            user_agent_hash=hash_for_audit(request.headers.get("User-Agent") if request else None),
            ip_address_hash=hash_for_audit(request_client_host(request)),
            status="active",
            created_at=now,
            last_used_at=now,
            expires_at=now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        )
        db.add(new_session)
        db.commit()
        db.refresh(new_session)
        self.audit_service.record(
            db, event_type="refresh_success", user_id=user.id, session_id=new_session.id, request=request
        )
        return IssuedTokens(
            access_token=create_access_token(user, session_id=new_session.id),
            refresh_token=refresh_token_new,
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            session=new_session,
        )

    def get_active_session(self, db: Session, *, session_id: str) -> AuthSession | None:
        now = utc_now()
        session = db.query(AuthSession).filter(AuthSession.id == session_id).first()
        if not session or session.status != "active" or _as_aware(session.expires_at) < now:
            return None
        return session

    def revoke_session(self, db: Session, *, session: AuthSession, reason: str = "logout") -> AuthSession:
        session.status = "revoked"
        session.revoked_at = utc_now()
        session.revoke_reason = reason
        db.add(session)
        db.commit()
        db.refresh(session)
        return session

    def revoke_all_user_sessions(self, db: Session, *, user_id: str, reason: str = "logout_all") -> int:
        now = utc_now()
        updated = (
            db.query(AuthSession)
            .filter(AuthSession.user_id == user_id, AuthSession.status == "active")
            .update({"status": "revoked", "revoked_at": now, "revoke_reason": reason}, synchronize_session=False)
        )
        db.commit()
        return updated

    def revoke_family(self, db: Session, *, family_id: str, reason: str) -> int:
        now = utc_now()
        updated = (
            db.query(AuthSession)
            .filter(AuthSession.refresh_token_family_id == family_id, AuthSession.status.in_(["active", "rotated"]))
            .update({"status": "compromised", "revoked_at": now, "revoke_reason": reason}, synchronize_session=False)
        )
        db.commit()
        return updated
