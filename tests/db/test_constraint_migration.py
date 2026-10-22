"""Migration 0005: existing data is tidied or refused, and the new rules then hold."""

import pytest
import sqlalchemy as sa
from alembic.config import Config

from alembic import command


@pytest.fixture()
def migrated(tmp_path):
    """(config, url, engine) for a throw-away SQLite database. Starts empty."""
    url = f"sqlite:///{tmp_path / 'constraints.db'}"
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    engine = sa.create_engine(url)
    yield cfg, url, engine
    engine.dispose()


def run(engine, sql, **params):
    with engine.begin() as conn:
        conn.execute(sa.text(sql), params)


def scalar(engine, sql):
    with engine.connect() as conn:
        return conn.execute(sa.text(sql)).scalar()


def column(engine, sql):
    with engine.connect() as conn:
        return [row[0] for row in conn.execute(sa.text(sql))]


# ------------------------------------------------------------------ tidying


def test_doctors_get_an_email_made_from_their_name(migrated):
    cfg, url, engine = migrated
    command.upgrade(cfg, "0004")
    run(engine, "INSERT INTO doctors (name, specialty) VALUES ('Dr. Amina Wanjiru', 'GP')")
    run(engine, "INSERT INTO doctors (name, specialty) VALUES ('Dr. Amina Wanjiru', 'GP')")
    run(engine, "INSERT INTO doctors (name, specialty) VALUES ('Dr. Zoë O''Neil', 'GP')")

    command.upgrade(cfg, "head")

    assert column(engine, "SELECT email FROM doctors ORDER BY id") == [
        "amina.wanjiru@example.com",
        "amina.wanjiru.2@example.com",  # same name twice: still unique
        "zo.oneil@example.com",
    ]


def test_patient_emails_are_lower_cased_and_duplicates_cleared(migrated):
    cfg, url, engine = migrated
    command.upgrade(cfg, "0004")
    for name, email in [
        ("First", "  Pat@Example.com "),
        ("Second", "pat@example.com"),
        ("Third", "PAT@EXAMPLE.COM"),
        ("Fourth", ""),
        ("Fifth", None),
        ("Sixth", "other@example.com"),
    ]:
        run(engine, "INSERT INTO patients (name, email) VALUES (:n, :e)", n=name, e=email)

    command.upgrade(cfg, "head")

    assert column(engine, "SELECT email FROM patients ORDER BY id") == [
        "pat@example.com",  # the first one keeps the address
        None,
        None,
        None,
        None,
        "other@example.com",
    ]


# ---------------------------------------------------------- refusing bad data

BAD_ROWS = [
    (
        "status",
        "INSERT INTO appointments (doctor_id, patient_id, start_time, end_time, status, created_at,"
        " updated_at, version) VALUES (1, 1, '2030-01-07 06:00:00', '2030-01-07 06:30:00', 'weird',"
        " '2030-01-01 00:00:00', '2030-01-01 00:00:00', 1)",
        "status other than",
    ),
    (
        "duration",
        "INSERT INTO appointments (doctor_id, patient_id, start_time, end_time, status, created_at,"
        " updated_at, version) VALUES (1, 1, '2030-01-07 06:00:00', '2030-01-07 06:45:00',"
        " 'booked', '2030-01-01 00:00:00', '2030-01-01 00:00:00', 1)",
        "30 minutes",
    ),
    (
        "weekday",
        "INSERT INTO working_hours (doctor_id, weekday, start_time, end_time)"
        " VALUES (1, 9, '09:00:00', '17:00:00')",
        "weekday outside",
    ),
    (
        "hours",
        "INSERT INTO working_hours (doctor_id, weekday, start_time, end_time)"
        " VALUES (1, 1, '17:00:00', '09:00:00')",
        "end before they start",
    ),
    (
        "login",
        "INSERT INTO users (email, password_hash, role, doctor_id, patient_id, created_at)"
        " VALUES ('x@example.com', 'h', 'doctor', NULL, NULL, '2030-01-01 00:00:00')",
        "wrong doctor or patient",
    ),
]


@pytest.mark.parametrize(("label", "bad_row", "message"), BAD_ROWS, ids=[b[0] for b in BAD_ROWS])
def test_existing_rows_that_break_a_new_rule_stop_the_migration(migrated, label, bad_row, message):
    cfg, url, engine = migrated
    command.upgrade(cfg, "0004")
    run(engine, "INSERT INTO doctors (name, specialty) VALUES ('Dr. T', 'GP')")
    run(engine, "INSERT INTO patients (name) VALUES ('Pat T')")
    run(engine, bad_row)

    with pytest.raises(RuntimeError, match="Cannot add the new database rule") as refused:
        command.upgrade(cfg, "head")
    assert message in str(refused.value)
    assert scalar(engine, "SELECT version_num FROM alembic_version") == "0004"  # nothing changed


# --------------------------------------------------------------- the new rules


@pytest.fixture()
def head(migrated):
    cfg, url, engine = migrated
    command.upgrade(cfg, "head")
    run(
        engine,
        "INSERT INTO doctors (name, specialty, email) VALUES ('Dr. T', 'GP', 'a@example.com')",
    )
    run(engine, "INSERT INTO patients (name, email) VALUES ('Pat T', 'p@example.com')")
    return cfg, engine


def insert_appointment(engine, status="booked", start="06:00:00", end="06:30:00"):
    run(
        engine,
        "INSERT INTO appointments (doctor_id, patient_id, start_time, end_time, status, created_at,"
        " updated_at, version) VALUES (1, 1, :s, :e, :status, '2030-01-01 00:00:00',"
        " '2030-01-01 00:00:00', 1)",
        s=f"2030-01-07 {start}",
        e=f"2030-01-07 {end}",
        status=status,
    )


def test_an_unknown_status_is_rejected(head):
    _, engine = head
    with pytest.raises(sa.exc.IntegrityError):
        insert_appointment(engine, status="pending")


def test_an_appointment_must_last_30_minutes(head):
    _, engine = head
    with pytest.raises(sa.exc.IntegrityError):
        insert_appointment(engine, end="06:45:00")
    insert_appointment(engine)  # exactly 30 minutes is fine


def test_the_slot_index_still_only_covers_active_appointments(head):
    """Rebuilding the table for the new rules must not turn the index into a plain unique one."""
    _, engine = head
    insert_appointment(engine, status="cancelled")
    insert_appointment(engine, status="cancelled")  # cancelled rows never block each other
    insert_appointment(engine, status="booked")  # ...or a new booking for the same time
    with pytest.raises(sa.exc.IntegrityError):
        insert_appointment(engine, status="rescheduled")  # but two active ones can't share it


def test_working_hours_must_be_a_real_weekday_in_order(head):
    _, engine = head
    sql = (
        "INSERT INTO working_hours (doctor_id, weekday, start_time, end_time)"
        " VALUES (1, :d, :s, :e)"
    )
    with pytest.raises(sa.exc.IntegrityError):
        run(engine, sql, d=7, s="09:00:00", e="17:00:00")
    with pytest.raises(sa.exc.IntegrityError):
        run(engine, sql, d=1, s="17:00:00", e="09:00:00")
    run(engine, sql, d=1, s="09:00:00", e="17:00:00")


def test_two_doctors_cannot_share_an_email(head):
    _, engine = head
    with pytest.raises(sa.exc.IntegrityError):
        run(
            engine,
            "INSERT INTO doctors (name, specialty, email) VALUES ('Other', 'GP', 'a@example.com')",
        )


def test_a_doctor_must_have_an_email(head):
    _, engine = head
    with pytest.raises(sa.exc.IntegrityError):
        run(engine, "INSERT INTO doctors (name, specialty) VALUES ('No Email', 'GP')")


def test_two_patients_cannot_share_an_email_but_several_can_have_none(head):
    _, engine = head
    with pytest.raises(sa.exc.IntegrityError):
        run(engine, "INSERT INTO patients (name, email) VALUES ('Copy', 'p@example.com')")
    run(engine, "INSERT INTO patients (name) VALUES ('No Email One')")
    run(engine, "INSERT INTO patients (name) VALUES ('No Email Two')")


def test_a_login_must_match_its_role(head):
    _, engine = head
    sql = (
        "INSERT INTO users (email, password_hash, role, doctor_id, patient_id, created_at)"
        " VALUES (:email, 'h', :role, :doctor, :patient, '2030-01-01 00:00:00')"
    )
    run(engine, sql, email="admin@example.com", role="admin", doctor=None, patient=None)
    run(engine, sql, email="doc@example.com", role="doctor", doctor=1, patient=None)
    run(engine, sql, email="pat@example.com", role="patient", doctor=None, patient=1)
    for role, doctor, patient in [
        ("admin", 1, None),
        ("doctor", None, 1),
        ("doctor", 1, 1),
        ("patient", None, None),
        ("owner", None, None),
    ]:
        with pytest.raises(sa.exc.IntegrityError):
            run(
                engine,
                sql,
                email=f"{role}{doctor}{patient}@example.com",
                role=role,
                doctor=doctor,
                patient=patient,
            )


def test_downgrading_removes_the_rules_and_the_doctor_email(head):
    cfg, engine = head
    command.downgrade(cfg, "0004")

    assert "email" not in {c["name"] for c in sa.inspect(engine).get_columns("doctors")}
    insert_appointment(engine, status="pending", end="06:45:00")  # no longer refused
    run(engine, "INSERT INTO patients (name, email) VALUES ('Copy', 'p@example.com')")
    # ...and the slot index is still the partial one
    insert_appointment(engine, status="cancelled")
    insert_appointment(engine, status="cancelled")
