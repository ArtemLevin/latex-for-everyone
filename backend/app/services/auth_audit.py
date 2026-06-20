import hashlib
import hmac

from fastapi import Request
from sqlalchemy.orm import Session

from app.config import settings
from app.models import AuthAuditLog
from app.time_utils import utc_now


def hash_for_audit(value: str | None) -> str | None:
    if not value:
        return None
    pepper = (settings.AUTH_REFRESH_TOKEN_PEPPER or settings.SECRET_KEY).encode()
    return hmac.new(pepper, value.encode(), hashlib.sha256).hexdigest()


def request_client_host(request: Request | None) -> str | None:
    return request.client.host if request and request.client else None


class AuthAuditService:
    def record(
        self,
        db: Session,
        *,
        event_type: str,
        user_id: str | None = None,
        session_id: str | None = None,
        request: Request | None = None,
        metadata: dict | None = None,
    ) -> AuthAuditLog:
        entry = AuthAuditLog(
            user_id=user_id,
            session_id=session_id,
            event_type=event_type,
            request_id=getattr(getattr(request, "state", None), "request_id", None),
            ip_address_hash=hash_for_audit(request_client_host(request)),
            user_agent_hash=hash_for_audit(request.headers.get("User-Agent") if request else None),
            metadata_json=metadata or {},
            created_at=utc_now(),
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        return entry
