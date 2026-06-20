import bcrypt

from app.config import settings

TRIVIAL_PASSWORDS = {"password", "password123", "1234567890", "qwerty", "qwerty12345"}


class PasswordValidationError(ValueError):
    pass


def hash_password(password: str) -> str:
    validate_password_strength(password)
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    if len(password.encode("utf-8")) > 72:
        return False
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def validate_password_strength(password: str) -> None:
    if len(password) < settings.AUTH_PASSWORD_MIN_LENGTH:
        raise PasswordValidationError(f"Password must be at least {settings.AUTH_PASSWORD_MIN_LENGTH} characters long.")
    if len(password.encode("utf-8")) > 72:
        raise PasswordValidationError("Password must be at most 72 bytes for bcrypt.")
    if not password.strip():
        raise PasswordValidationError("Password must not be blank.")
    if password.strip().lower() in TRIVIAL_PASSWORDS:
        raise PasswordValidationError("Password is too common.")
