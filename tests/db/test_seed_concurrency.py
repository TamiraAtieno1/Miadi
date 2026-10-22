"""Two instances seeding at the same moment must not create the demo data twice.

Needs real concurrent connections, so it only runs on Postgres (CI always does).

To make the race deterministic, inserting a doctor is slowed down. Without the advisory
lock, both seeders see an empty table during that pause and both insert; remove the lock
from `seed_if_empty` and this test fails.
"""

import time
from threading import Barrier, Thread

import pytest
from sqlalchemy import event

from app.database import SessionLocal, engine
from app.models import Doctor, Patient
from app.seed import seed_if_empty

pytestmark = pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="needs concurrent connections (Postgres)",
)

SEEDERS = 4


def test_simultaneous_seeders_create_the_data_exactly_once(db):
    def slow_insert(mapper, connection, target):
        time.sleep(0.2)

    event.listen(Doctor, "before_insert", slow_insert)
    start = Barrier(SEEDERS, timeout=20)
    errors = []

    def seed():
        try:
            with SessionLocal() as session:
                start.wait()
                seed_if_empty(session)
        except Exception as error:  # noqa: BLE001  (reported below)
            errors.append(error)

    threads = [Thread(target=seed) for _ in range(SEEDERS)]
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)
    finally:
        event.remove(Doctor, "before_insert", slow_insert)

    assert errors == []
    db.expire_all()
    assert db.query(Doctor).count() == 5
    assert db.query(Patient).count() == 1
