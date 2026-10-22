import pytest

from app.errors import EmailTakenError, InvalidAccountError, InvalidCredentialsError
from app.models import ROLE_PATIENT, Patient, User
from app.services import accounts


def test_register_creates_a_patient_and_a_login(db):
    user = accounts.register_patient(db, "  Wanjiku Mwangi ", " Wanjiku@Example.com ", "longenough")

    assert user.role == ROLE_PATIENT
    assert user.email == "wanjiku@example.com"
    assert user.patient.name == "Wanjiku Mwangi"
    assert db.get(Patient, user.patient_id).email == "wanjiku@example.com"
    assert user.password_hash != "longenough"


@pytest.mark.parametrize(
    ("name", "email", "password"),
    [
        ("", "a@example.com", "longenough"),
        ("x" * 101, "a@example.com", "longenough"),
        ("Ann", "not-an-email", "longenough"),
        ("Ann", "a b@example.com", "longenough"),
        ("Ann", "a@example.com", "short"),
    ],
)
def test_register_rejects_bad_details(db, name, email, password):
    with pytest.raises(InvalidAccountError):
        accounts.register_patient(db, name, email, password)


def test_register_rejects_a_taken_email_in_any_case(db):
    accounts.register_patient(db, "Ann", "ann@example.com", "longenough")
    with pytest.raises(EmailTakenError):
        accounts.register_patient(db, "Ann Two", "ANN@example.com", "longenough")


def test_register_reports_a_race_on_the_email(db, monkeypatch):
    """Two sign-ups can both pass the check; the unique index lets only one in."""
    accounts.register_patient(db, "Ann", "ann@example.com", "longenough")
    monkeypatch.setattr(db, "scalar", lambda *args, **kwargs: None)
    with pytest.raises(EmailTakenError):
        accounts.register_patient(db, "Ann Two", "ann@example.com", "longenough")


def test_authenticate_accepts_the_right_password(db):
    created = accounts.register_patient(db, "Ann", "ann@example.com", "longenough")
    assert accounts.authenticate(db, " ANN@example.com", "longenough").id == created.id


def test_authenticate_gives_one_error_for_unknown_email_and_wrong_password(db):
    accounts.register_patient(db, "Ann", "ann@example.com", "longenough")
    with pytest.raises(InvalidCredentialsError) as wrong:
        accounts.authenticate(db, "ann@example.com", "nope")
    with pytest.raises(InvalidCredentialsError) as unknown:
        accounts.authenticate(db, "nobody@example.com", "longenough")
    assert wrong.value.message == unknown.value.message


def test_ensure_user_creates_once(db):
    assert accounts.ensure_user(db, "Admin@Example.com", "pw-123456", "admin") is True
    assert accounts.ensure_user(db, "admin@example.com", "other-pw-1", "admin") is False
    assert db.query(User).count() == 1


def test_ensure_user_tolerates_a_parallel_seeder_creating_the_same_account(db, monkeypatch):
    accounts.ensure_user(db, "admin@example.com", "pw-123456", "admin")
    # Pretend our "is it taken?" check ran before the other seeder committed.
    monkeypatch.setattr(db, "scalar", lambda *args, **kwargs: None)

    assert accounts.ensure_user(db, "admin@example.com", "pw-123456", "admin") is False


def test_register_refuses_an_email_already_on_a_patient_record_made_through_the_api(db):
    """Signing up must not hand a stranger a patient record that someone else created."""
    db.add(Patient(name="Created By Clinic", email="walkin@example.com"))
    db.commit()

    with pytest.raises(EmailTakenError):
        accounts.register_patient(db, "Someone Else", "walkin@example.com", "longenough")
