import pytest

from app.errors import StaleVersionError
from app.services import booking
from tests.services.helpers import MON, NOW, book, local


def test_a_matching_version_is_accepted(db, world):
    appt = book(db, world, local(MON, 9))
    assert booking.cancel_appointment(db, appt.id, "x", appt.version, now=NOW).status == "cancelled"


@pytest.mark.parametrize("offset", [-1, 1, 5])
def test_any_other_version_is_refused_before_anything_changes(db, world, offset):
    appt = book(db, world, local(MON, 9))

    with pytest.raises(StaleVersionError):
        booking.cancel_appointment(db, appt.id, "x", appt.version + offset, now=NOW)
    with pytest.raises(StaleVersionError):
        booking.reschedule_appointment(db, appt.id, local(MON, 10), appt.version + offset, now=NOW)

    db.refresh(appt)
    assert appt.status == "booked"
    assert appt.start_time.hour == 6  # 09:00 EAT, untouched
    assert appt.version == 1


def test_the_version_is_checked_before_the_state(db, world):
    """A stale screen is told the appointment changed, not just that it is already cancelled."""
    appt = book(db, world, local(MON, 9))
    seen = appt.version
    booking.cancel_appointment(db, appt.id, "first", seen, now=NOW)

    with pytest.raises(StaleVersionError):
        booking.cancel_appointment(db, appt.id, "second", seen, now=NOW)


def test_an_unknown_appointment_is_still_not_found(db, world):
    from app.errors import NotFoundError

    with pytest.raises(NotFoundError):
        booking.cancel_appointment(db, 999, "x", 1, now=NOW)
