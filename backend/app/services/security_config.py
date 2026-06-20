from app.config import settings


DEFAULT_SECRET_KEY = "change-me-in-production-please"
SUPPORTED_AUTH_MODES = {"local", "password", "trusted_proxy"}


class SecurityConfigurationError(RuntimeError):
    """Raised when startup detects unsafe security settings."""


def _is_production_environment() -> bool:
    return settings.DEPLOYMENT_ENV.strip().lower() in {"prod", "production"}


def _has_wildcard_allowed_hosts() -> bool:
    return any(host.strip() == "*" for host in settings.ALLOWED_HOSTS)


def _has_wildcard_cors_origins() -> bool:
    return any(origin.strip() == "*" for origin in settings.CORS_ORIGINS)


def validate_security_settings() -> None:
    """Fail fast for production deployments with unsafe auth/host settings."""
    auth_mode = settings.AUTH_MODE.strip().lower()
    if auth_mode not in SUPPORTED_AUTH_MODES:
        raise SecurityConfigurationError("AUTH_MODE must be one of: local, password, trusted_proxy")

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
    if auth_mode == "password":
        if not settings.AUTH_REFRESH_TOKEN_PEPPER:
            raise SecurityConfigurationError(
                "AUTH_REFRESH_TOKEN_PEPPER is required when AUTH_MODE=password in production"
            )
        if settings.ACCESS_TOKEN_EXPIRE_MINUTES > 60:
            raise SecurityConfigurationError("ACCESS_TOKEN_EXPIRE_MINUTES must be <= 60 in production password auth")
        if settings.REFRESH_TOKEN_EXPIRE_DAYS > 90:
            raise SecurityConfigurationError("REFRESH_TOKEN_EXPIRE_DAYS must be <= 90 in production password auth")
        if settings.AUTH_COOKIE_MODE and not settings.AUTH_COOKIE_SECURE:
            raise SecurityConfigurationError("AUTH_COOKIE_SECURE=true is required for production cookie auth")
        if settings.AUTH_COOKIE_MODE and _has_wildcard_cors_origins():
            raise SecurityConfigurationError("CORS_ORIGINS must not contain '*' for production cookie auth")

    if settings.COMPILE_EXECUTION_MODE.strip().lower() != "sandbox":
        raise SecurityConfigurationError("COMPILE_EXECUTION_MODE must be sandbox in production")
    if not settings.COMPILE_SANDBOX_NETWORK_DISABLED:
        raise SecurityConfigurationError("Compile sandbox network must be disabled in production")
    if not settings.COMPILE_SANDBOX_READ_ONLY_ROOTFS:
        raise SecurityConfigurationError("Compile sandbox root filesystem must be read-only in production")
    if not settings.COMPILE_SANDBOX_CAP_DROP_ALL:
        raise SecurityConfigurationError("Compile sandbox must drop all Linux capabilities in production")
    if not settings.COMPILE_SANDBOX_NO_NEW_PRIVILEGES:
        raise SecurityConfigurationError("Compile sandbox must set no-new-privileges in production")
    if settings.COMPILE_SANDBOX_SHELL_ESCAPE.strip().lower() != "disabled":
        raise SecurityConfigurationError("LaTeX shell escape must be disabled in production")
    if (
        not settings.COMPILE_SANDBOX_MEMORY
        or settings.COMPILE_SANDBOX_CPUS <= 0
        or settings.COMPILE_SANDBOX_PIDS_LIMIT <= 0
    ):
        raise SecurityConfigurationError("Compile sandbox memory, CPU and PIDs limits are required in production")
