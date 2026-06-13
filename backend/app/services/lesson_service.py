from datetime import datetime

from sqlalchemy.orm import Session

from app.models import Lesson, Pupil
from app.schemas import LessonCreate, LessonUpdate, PupilCreate, PupilUpdate
from app.time_utils import utc_now


class LessonDomainError(Exception):
    """Base error for pupil and lesson workflows."""


class PupilNotFoundError(LessonDomainError):
    """Raised when a pupil does not exist in the current teacher scope."""


class LessonNotFoundError(LessonDomainError):
    """Raised when a lesson does not exist in the current teacher scope."""


class LessonValidationError(LessonDomainError):
    """Raised when a lesson request is invalid for the current state."""


class PupilService:
    """Business rules for pupil CRUD under the placeholder teacher scope."""

    def list_pupils(self, db: Session, teacher_id: str, *, skip: int = 0, limit: int = 100) -> list[Pupil]:
        return (
            db.query(Pupil)
            .filter(Pupil.teacher_id == teacher_id)
            .order_by(Pupil.updated_at.desc(), Pupil.display_name.asc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def create_pupil(self, db: Session, teacher_id: str, pupil_data: PupilCreate) -> Pupil:
        pupil = Pupil(
            teacher_id=teacher_id,
            display_name=pupil_data.display_name,
            notes=pupil_data.notes,
        )
        db.add(pupil)
        db.commit()
        db.refresh(pupil)
        return pupil

    def get_pupil(self, db: Session, teacher_id: str, pupil_id: str) -> Pupil:
        pupil = db.query(Pupil).filter(Pupil.id == pupil_id, Pupil.teacher_id == teacher_id).first()
        if not pupil:
            raise PupilNotFoundError("Pupil not found")
        return pupil

    def update_pupil(self, db: Session, teacher_id: str, pupil_id: str, pupil_data: PupilUpdate) -> Pupil:
        pupil = self.get_pupil(db, teacher_id, pupil_id)
        update_data = pupil_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(pupil, key, value)
        pupil.updated_at = utc_now()
        db.commit()
        db.refresh(pupil)
        return pupil

    def delete_pupil(self, db: Session, teacher_id: str, pupil_id: str) -> str:
        pupil = self.get_pupil(db, teacher_id, pupil_id)
        display_name = pupil.display_name
        db.delete(pupil)
        db.commit()
        return display_name


class LessonService:
    """Business rules for lesson CRUD under the placeholder teacher scope."""

    def create_lesson(self, db: Session, teacher_id: str, lesson_data: LessonCreate) -> Lesson:
        pupil = db.query(Pupil).filter(Pupil.id == lesson_data.pupil_id, Pupil.teacher_id == teacher_id).first()
        if not pupil:
            raise PupilNotFoundError("Pupil not found")

        lesson = Lesson(
            pupil_id=pupil.id,
            teacher_id=teacher_id,
            topic=lesson_data.topic,
            lesson_date=lesson_data.lesson_date or utc_now(),
        )
        db.add(lesson)
        db.commit()
        db.refresh(lesson)
        return lesson

    def list_lessons(
        self,
        db: Session,
        teacher_id: str,
        *,
        pupil_id: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Lesson]:
        query = db.query(Lesson).filter(Lesson.teacher_id == teacher_id)
        if pupil_id is not None:
            pupil = db.query(Pupil).filter(Pupil.id == pupil_id, Pupil.teacher_id == teacher_id).first()
            if not pupil:
                raise PupilNotFoundError("Pupil not found")
            query = query.filter(Lesson.pupil_id == pupil_id)
        if date_from is not None:
            query = query.filter(Lesson.lesson_date >= date_from)
        if date_to is not None:
            query = query.filter(Lesson.lesson_date <= date_to)
        return query.order_by(Lesson.lesson_date.desc(), Lesson.updated_at.desc()).offset(skip).limit(limit).all()

    def get_lesson(self, db: Session, teacher_id: str, lesson_id: str) -> Lesson:
        lesson = db.query(Lesson).filter(Lesson.id == lesson_id, Lesson.teacher_id == teacher_id).first()
        if not lesson:
            raise LessonNotFoundError("Lesson not found")
        return lesson

    def update_lesson(self, db: Session, teacher_id: str, lesson_id: str, lesson_data: LessonUpdate) -> Lesson:
        lesson = self.get_lesson(db, teacher_id, lesson_id)
        update_data = lesson_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(lesson, key, value)
        lesson.updated_at = utc_now()
        db.commit()
        db.refresh(lesson)
        return lesson

    def delete_lesson(self, db: Session, teacher_id: str, lesson_id: str) -> str:
        lesson = self.get_lesson(db, teacher_id, lesson_id)
        topic = lesson.topic
        db.delete(lesson)
        db.commit()
        return topic
