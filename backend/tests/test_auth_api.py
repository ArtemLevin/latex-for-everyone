import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.models import AuthAuditLog, AuthSession, Project, User
from app.services.auth_passwords import (
    PasswordValidationError,
    hash_password,
    validate_password_strength,
    verify_password,
)
from app.services.auth_tokens import (
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_refresh_token,
)
from app.services.users import UserService

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_auth_latexed.db"
engine_test = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionTesting = sessionmaker(autocommit=False, autoflush=False, bind=engine_test)


def override_get_db():
    db = SessionTesting()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup_db(monkeypatch):
    previous_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.drop_all(bind=engine_test)
    Base.metadata.create_all(bind=engine_test)
    monkeypatch.setattr(settings, "AUTH_MODE", "password")
    monkeypatch.setattr(settings, "SECRET_KEY", "test-secret-key-that-is-long-enough")
    monkeypatch.setattr(settings, "AUTH_REFRESH_TOKEN_PEPPER", "test-refresh-pepper")
    monkeypatch.setattr(settings, "AUTH_COOKIE_SECURE", False)
    monkeypatch.setattr(settings, "AUTH_REGISTRATION_ENABLED", False)
    yield
    Base.metadata.drop_all(bind=engine_test)
    if previous_override is not None:
        app.dependency_overrides[get_db] = previous_override
    else:
        app.dependency_overrides.pop(get_db, None)


client = TestClient(app)


def create_password_user(email="teacher@example.com", password="correct horse battery"):
    db = SessionTesting()
    try:
        user = UserService().create_user(
            db,
            email=email,
            display_name="Teacher",
            password_hash=hash_password(password),
            auth_provider="password",
            is_verified=True,
        )
        return user.id
    finally:
        db.close()


def test_hash_password_not_plaintext_and_verify():
    password_hash = hash_password("correct horse battery")

    assert password_hash != "correct horse battery"
    assert verify_password("correct horse battery", password_hash)
    assert not verify_password("wrong password", password_hash)


def test_validate_password_rejects_short_and_trivial(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_PASSWORD_MIN_LENGTH", 10)

    with pytest.raises(PasswordValidationError):
        validate_password_strength("short")
    with pytest.raises(PasswordValidationError):
        validate_password_strength("1234567890")


def test_access_and_refresh_token_helpers():
    user_id = create_password_user()
    db = SessionTesting()
    try:
        user = db.query(User).filter(User.id == user_id).one()
        token = create_access_token(user, session_id="session-1")
        claims = decode_access_token(token)
        refresh = generate_refresh_token()
        refresh_hash = hash_refresh_token(refresh)
    finally:
        db.close()

    assert claims["sub"] == user_id
    assert claims["sid"] == "session-1"
    assert claims["type"] == "access"
    assert refresh_hash == hash_refresh_token(refresh)
    assert refresh_hash != refresh


def test_login_success_sets_refresh_cookie_and_audit_log():
    user_id = create_password_user()

    response = client.post(
        "/api/auth/login", json={"email": "teacher@example.com", "password": "correct horse battery"}
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert payload["access_token"]
    assert payload["user"]["id"] == user_id
    assert settings.AUTH_REFRESH_COOKIE_NAME in response.cookies

    db = SessionTesting()
    try:
        assert db.query(AuthSession).filter(AuthSession.user_id == user_id, AuthSession.status == "active").count() == 1
        assert (
            db.query(AuthAuditLog)
            .filter(AuthAuditLog.event_type == "login_success", AuthAuditLog.user_id == user_id)
            .count()
            == 1
        )
    finally:
        db.close()


def test_login_wrong_password_returns_401_without_password_in_audit():
    create_password_user()

    response = client.post("/api/auth/login", json={"email": "teacher@example.com", "password": "wrong password"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"
    db = SessionTesting()
    try:
        audit = db.query(AuthAuditLog).filter(AuthAuditLog.event_type == "login_failed").one()
        assert "wrong password" not in str(audit.metadata_json)
    finally:
        db.close()


def test_refresh_rotates_token_and_reuse_compromises_family():
    create_password_user()
    login = client.post("/api/auth/login", json={"email": "teacher@example.com", "password": "correct horse battery"})
    old_refresh = login.cookies[settings.AUTH_REFRESH_COOKIE_NAME]

    refresh = client.post("/api/auth/refresh", json={"refresh_token": old_refresh})
    reuse = client.post("/api/auth/refresh", json={"refresh_token": old_refresh})

    assert refresh.status_code == 200
    assert refresh.json()["access_token"] != login.json()["access_token"]
    assert reuse.status_code == 401

    db = SessionTesting()
    try:
        statuses = {session.status for session in db.query(AuthSession).all()}
        assert "compromised" in statuses
        assert db.query(AuthAuditLog).filter(AuthAuditLog.event_type == "refresh_reuse_detected").count() == 1
    finally:
        db.close()


def test_me_logout_and_logout_all():
    create_password_user()
    login1 = client.post("/api/auth/login", json={"email": "teacher@example.com", "password": "correct horse battery"})
    login2 = client.post("/api/auth/login", json={"email": "teacher@example.com", "password": "correct horse battery"})
    headers1 = {"Authorization": f"Bearer {login1.json()['access_token']}"}
    headers2 = {"Authorization": f"Bearer {login2.json()['access_token']}"}

    me = client.get("/api/auth/me", headers=headers1)
    logout = client.post("/api/auth/logout", headers=headers1)
    me_after_logout = client.get("/api/auth/me", headers=headers1)
    logout_all = client.post("/api/auth/logout-all", headers=headers2)
    me_after_logout_all = client.get("/api/auth/me", headers=headers2)

    assert me.status_code == 200
    assert logout.status_code == 200
    assert logout.json()["revoked_sessions"] == 1
    assert me_after_logout.status_code == 401
    assert logout_all.status_code == 200
    assert logout_all.json()["revoked_sessions"] == 1
    assert me_after_logout_all.status_code == 401


def test_register_disabled_by_default_and_enabled_registration(monkeypatch):
    disabled = client.post(
        "/api/auth/register",
        json={"email": "new@example.com", "password": "correct horse battery", "display_name": "New"},
    )
    monkeypatch.setattr(settings, "AUTH_REGISTRATION_ENABLED", True)
    enabled = client.post(
        "/api/auth/register",
        json={"email": "new@example.com", "password": "correct horse battery", "display_name": "New"},
    )

    assert disabled.status_code == 404
    assert enabled.status_code == 201
    assert enabled.json()["user"]["email"] == "new@example.com"


def test_local_auth_creates_local_user_and_preserves_owner_scope(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_MODE", "local")
    monkeypatch.setattr(settings, "LOCAL_USER_ID", "local-teacher")

    response = client.post("/api/projects/", json={"name": "Local User Project"})

    assert response.status_code == 201
    assert response.json()["owner_id"] == "local-teacher"
    db = SessionTesting()
    try:
        user = db.query(User).filter(User.id == "local-teacher").one()
        assert user.auth_provider == "local"
    finally:
        db.close()


def test_trusted_proxy_auto_provisions_user_and_rejects_untrusted(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_MODE", "trusted_proxy")
    monkeypatch.setattr(settings, "TRUSTED_PROXY_IPS", ["testclient"])
    monkeypatch.setattr(settings, "TRUSTED_USER_HEADER", "X-Latexed-User")
    monkeypatch.setattr(settings, "TRUSTED_PROXY_AUTO_PROVISION_USERS", True)

    allowed = client.post("/api/projects/", json={"name": "Proxy Project"}, headers={"X-Latexed-User": "teacher-a"})
    monkeypatch.setattr(settings, "TRUSTED_PROXY_IPS", ["192.0.2.10"])
    denied = client.get("/api/projects/", headers={"X-Latexed-User": "teacher-a"})

    assert allowed.status_code == 201
    assert allowed.json()["owner_id"] == "teacher-a"
    assert denied.status_code == 403
    db = SessionTesting()
    try:
        user = db.query(User).filter(User.id == "teacher-a").one()
        assert user.auth_provider == "trusted_proxy"
        assert user.external_subject == "teacher-a"
    finally:
        db.close()


def test_existing_project_owner_scoping_still_works_with_password_auth():
    user_id = create_password_user()
    other_id = create_password_user(email="other@example.com")
    db = SessionTesting()
    try:
        db.add(Project(id="00000000-0000-0000-0000-000000000001", name="Owned", owner_id=user_id))
        db.commit()
    finally:
        db.close()
    login_owner = client.post(
        "/api/auth/login", json={"email": "teacher@example.com", "password": "correct horse battery"}
    )
    login_other = client.post(
        "/api/auth/login", json={"email": "other@example.com", "password": "correct horse battery"}
    )

    owner_get = client.get(
        "/api/projects/00000000-0000-0000-0000-000000000001",
        headers={"Authorization": f"Bearer {login_owner.json()['access_token']}"},
    )
    other_get = client.get(
        "/api/projects/00000000-0000-0000-0000-000000000001",
        headers={"Authorization": f"Bearer {login_other.json()['access_token']}"},
    )

    assert other_id != user_id
    assert owner_get.status_code == 200
    assert other_get.status_code == 404
