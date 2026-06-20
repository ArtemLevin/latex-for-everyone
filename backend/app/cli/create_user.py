import argparse
import getpass

from app.database import Base, SessionLocal, engine
from app.models import User
from app.services.auth_passwords import PasswordValidationError, hash_password
from app.services.users import UserService, normalize_email


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a Latexed password user.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", default=None)
    parser.add_argument("--display-name", default=None)
    parser.add_argument("--role", default="teacher", choices=["teacher", "admin"])
    parser.add_argument("--adopt-legacy-id", default=None)
    args = parser.parse_args()

    password = args.password or getpass.getpass("Password: ")
    try:
        password_hash = hash_password(password)
    except PasswordValidationError as exc:
        raise SystemExit(str(exc)) from exc

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        service = UserService()
        if service.get_by_email(db, args.email):
            raise SystemExit("User with this email already exists")
        if args.adopt_legacy_id:
            existing = db.query(User).filter(User.id == args.adopt_legacy_id).first()
            if existing:
                existing.email = args.email.strip()
                existing.normalized_email = normalize_email(args.email)
                existing.display_name = args.display_name or existing.display_name or args.email.strip()
                existing.password_hash = password_hash
                existing.auth_provider = "password"
                existing.role = args.role
                existing.is_active = True
                existing.is_verified = True
                db.add(existing)
                db.commit()
                print(f"Updated user {existing.id}")
                return 0
        user = service.create_user(
            db,
            user_id=args.adopt_legacy_id,
            email=args.email,
            display_name=args.display_name,
            password_hash=password_hash,
            auth_provider="password",
            role=args.role,
            is_verified=True,
        )
        print(f"Created user {user.id} ({user.email})")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
