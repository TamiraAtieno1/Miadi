"""Creating patient records."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import EmailTakenError
from app.models import Patient

EMAIL_CONSTRAINT = "uq_patients_email"


def _is_email_clash(error: IntegrityError) -> bool:
    """True only when the database rejected a duplicate patient email."""
    diagnostics = getattr(error.orig, "diag", None)  # PostgreSQL names the constraint
    if diagnostics is not None:
        return diagnostics.constraint_name == EMAIL_CONSTRAINT
    return "patients.email" in str(error.orig)  # SQLite names the column


def create_patient(
    db: Session, name: str, phone: str | None = None, email: str | None = None
) -> Patient:
    """Create a patient. Two patients can't share an email address."""
    patient = Patient(name=name, phone=phone, email=email)
    db.add(patient)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        if not _is_email_clash(error):
            raise
        raise EmailTakenError("A patient with that email address already exists.") from error
    db.refresh(patient)
    return patient
