from app.config import settings


DEFAULT_SECRET_KEY = "change-me-in-production-please"
SUPPORTED_AUTH_MODES = {"local", "trusted_proxy"}


class SecurityConfigurationError(RuntimeError):
    """Raised when startup detects unsafe security settings."""


def _is_production_environment() -> bool:
    return settings.DEPLOYMENT_ENV.strip().lower() in {"prod", "production"}


def _has_wildcard_allowed_hosts() -> bool:
    return any(host.strip() == "*" for host in settings.ALLOWED_HOSTS)


def validate_security_settings() -> None:
    """Fail fast for production deployments with unsafe auth/host settings."""
    auth_mode = settings.AUTH_MODE.strip().lower()
    if auth_mode not in SUPPORTED_AUTH_MODES:
        raise SecurityConfigurationError("AUTH_MODE must be one of: local, trusted_proxy")

    if auth_mode == "trusted_proxy":
        if not settings.TRUSTED_USER_HEADER.strip():
            raise SecurityConfigurationError("TRUSTED_USER_HEADER is required when AUTH_MODE=trusted_proxy")
        if not settings.TRUSTED_PROXY_IPS:
            raise SecurityConfigurationError("TRUSTED_PROXY_IPS is required when AUTH_MODE=trusted_proxy")

    if not _is_production_environment():
        return

    if settings.SECRET_KEY == DEFAULT_SECRET_KEY:
        raise SecurityConfigurationError("SECRET_KEY must be changed for production deployments")
    if _has_wildcard_allowed_hosts():
        raise SecurityConfigurationError("ALLOWED_HOSTS must not contain '*' in production deployments")
    if auth_mode == "local" and not settings.ALLOW_PRODUCTION_LOCAL_AUTH:
        raise SecurityConfigurationError("AUTH_MODE=local in production requires ALLOW_PRODUCTION_LOCAL_AUTH=true")
