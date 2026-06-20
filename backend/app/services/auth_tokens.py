import hashlib
import hmac
import secrets
from datetime import timedelta

from jose import JWTError, jwt

from app.config import settings
from app.models import User
from app.time_utils import utc_now


class AccessTokenError(ValueError):
    pass


def create_access_token(user: User, *, session_id: str) -> str:
    now = utc_now()
    claims = {
        "sub": user.id,
        "sid": session_id,
        "role": user.role,
        "type": "access",
        "iss": settings.AUTH_TOKEN_ISSUER,
        "aud": settings.AUTH_TOKEN_AUDIENCE,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)).timestamp()),
    }
    return jwt.encode(claims, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        claims = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            issuer=settings.AUTH_TOKEN_ISSUER,
            audience=settings.AUTH_TOKEN_AUDIENCE,
        )
    except JWTError as exc:
        raise AccessTokenError("Invalid token") from exc
    if claims.get("type") != "access" or not claims.get("sub") or not claims.get("sid"):
        raise AccessTokenError("Invalid token")
    return claims


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(64)


def hash_refresh_token(token: str) -> str:
    pepper = (settings.AUTH_REFRESH_TOKEN_PEPPER or settings.SECRET_KEY).encode()
    return hmac.new(pepper, token.encode(), hashlib.sha256).hexdigest()
