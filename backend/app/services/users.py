from sqlalchemy.orm import Session

from app.models import User
from app.time_utils import utc_now


def normalize_email(email: str) -> str:
    return email.strip().lower()


class UserService:
    def get_by_id(self, db: Session, user_id: str) -> User | None:
        return db.query(User).filter(User.id == user_id).first()

    def get_by_email(self, db: Session, email: str) -> User | None:
        return db.query(User).filter(User.normalized_email == normalize_email(email)).first()

    def get_by_provider_subject(self, db: Session, *, provider: str, subject: str) -> User | None:
        return db.query(User).filter(User.auth_provider == provider, User.external_subject == subject).first()

    def create_user(
        self,
        db: Session,
        *,
        user_id: str | None = None,
        email: str | None = None,
        display_name: str | None = None,
        password_hash: str | None = None,
        auth_provider: str = "password",
        external_subject: str | None = None,
        role: str = "teacher",
        is_verified: bool = False,
    ) -> User:
        normalized_email = normalize_email(email) if email else None
        user = User(
            id=user_id,
            email=email.strip() if email else None,
            normalized_email=normalized_email,
            display_name=display_name or (email.strip() if email else external_subject),
            password_hash=password_hash,
            auth_provider=auth_provider,
            external_subject=external_subject,
            role=role,
            is_active=True,
            is_verified=is_verified,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    def ensure_local_user(self, db: Session, *, identity: str) -> User:
        user = self.get_by_id(db, identity)
        if user:
            return user
        return self.create_user(
            db,
            user_id=identity,
            display_name=identity,
            auth_provider="local",
            external_subject=identity,
            role="teacher",
            is_verified=True,
        )

    def ensure_trusted_proxy_user(self, db: Session, *, identity: str, role: str) -> User:
        user = self.get_by_provider_subject(db, provider="trusted_proxy", subject=identity)
        if user:
            return user
        # Preserve legacy owner scoping by using the external subject as user id when available.
        existing_id_user = self.get_by_id(db, identity)
        if existing_id_user:
            existing_id_user.auth_provider = "trusted_proxy"
            existing_id_user.external_subject = identity
            existing_id_user.updated_at = utc_now()
            db.add(existing_id_user)
            db.commit()
            db.refresh(existing_id_user)
            return existing_id_user
        return self.create_user(
            db,
            user_id=identity,
            display_name=identity,
            auth_provider="trusted_proxy",
            external_subject=identity,
            role=role,
            is_verified=True,
        )
