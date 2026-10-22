"""Logins: sign in, patient sign-up and creating demo accounts."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import EmailTakenError, InvalidAccountError, InvalidCredentialsError
from app.models import ROLE_PATIENT, Patient, User
from app.security import DUMMY_HASH, hash_password, verify_password

MIN_PASSWORD_LENGTH = 8


def normalise_email(email: str) -> str:
    """Emails are compared in lower case without surrounding spaces."""
    return email.strip().lower()


def authenticate(db: Session, email: str, password: str) -> User:
    """Return the user for a correct email and password, otherwise raise.

    An unknown email and a wrong password give the same error and take about the
    same time, so the form never reveals which emails have accounts.
    """
    user = db.scalar(select(User).where(User.email == normalise_email(email)))
    stored = user.password_hash if user else DUMMY_HASH
    if not verify_password(password, stored) or user is None:
        raise InvalidCredentialsError("That email and password don't match. Please try again.")
    return user


def register_patient(db: Session, name: str, email: str, password: str) -> User:
    """Create a patient record together with its login."""
    name = name.strip()
    email = normalise_email(email)
    if not name or len(name) > 100:
        raise InvalidAccountError("Please enter your full name (up to 100 characters).")
    if "@" not in email or " " in email or len(email) > 255:
        raise InvalidAccountError("Please enter a valid email address.")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise InvalidAccountError(f"Your password needs at least {MIN_PASSWORD_LENGTH} characters.")
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise EmailTakenError("There is already an account with that email. Try signing in.")

    patient = Patient(name=name, email=email)
    user = User(
        email=email,
        password_hash=hash_password(password),
        role=ROLE_PATIENT,
        patient=patient,
    )
    db.add_all([patient, user])
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise EmailTakenError(
            "There is already an account with that email. Try signing in."
        ) from error
    return user


def ensure_user(
    db: Session,
    email: str,
    password: str,
    role: str,
    doctor_id: int | None = None,
    patient_id: int | None = None,
) -> bool:
    """Create an account if its email is unused. Returns True when this call created it."""
    email = normalise_email(email)
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        return False
    db.add(
        User(
            email=email,
            password_hash=hash_password(password),
            role=role,
            doctor_id=doctor_id,
            patient_id=patient_id,
        )
    )
    try:
        db.commit()
    except IntegrityError:
        # Another seeder created the same account between our check and our insert.
        db.rollback()
        return False
    return True
