from app.models import ROLE_ADMIN, ROLE_DOCTOR, ROLE_PATIENT, User
from app.security import verify_password
from app.seed import ADMIN_EMAIL, doctor_email, seed_if_empty, seed_users_if_missing


def test_doctor_email_drops_the_title():
    assert doctor_email("Dr. Amina Wanjiru") == "amina.wanjiru@example.com"
    assert doctor_email("dr David  Kamau") == "david.kamau@example.com"


def test_seeding_users_creates_one_login_per_person_and_is_repeatable(db):
    seed_if_empty(db)
    seed_users_if_missing(db)
    seed_users_if_missing(db)

    users = db.query(User).all()
    assert len(users) == 7  # admin + 5 doctors + the demo patient
    by_role = {
        role: [u for u in users if u.role == role]
        for role in (ROLE_ADMIN, ROLE_DOCTOR, ROLE_PATIENT)
    }
    assert [u.email for u in by_role[ROLE_ADMIN]] == [ADMIN_EMAIL]
    assert all(u.doctor_id for u in by_role[ROLE_DOCTOR])
    assert by_role[ROLE_PATIENT][0].patient.name == "Demo Patient"


def test_demo_password_comes_from_the_environment(db, monkeypatch):
    monkeypatch.setenv("DEMO_PASSWORD", "something-private")
    seed_if_empty(db)
    seed_users_if_missing(db)
    admin = db.query(User).filter_by(email=ADMIN_EMAIL).one()
    assert verify_password("something-private", admin.password_hash)
    assert not verify_password("miadi-demo", admin.password_hash)


def test_seeding_users_without_a_demo_patient_still_works(db):
    seed_users_if_missing(db)  # empty database: only the admin exists
    assert [u.email for u in db.query(User).all()] == [ADMIN_EMAIL]


def test_the_seed_command_creates_the_data_and_the_logins(db):
    from app import seed

    seed.main()
    seed.main()  # safe to repeat

    assert db.query(User).count() == 7
