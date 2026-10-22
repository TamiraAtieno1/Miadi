"""The API reports a concurrent change as a clean 409."""

from sqlalchemy import update

from app.models import Appointment
from app.services import booking
from tests.api.helpers import book, future_slot


def test_a_concurrent_change_returns_409_with_a_code(client, monkeypatch):
    appt_id = book(client, future_slot(9)).json()["id"]
    real = booking.get_appointment

    def load_then_lose_the_race(db, appointment_id):
        appointment = real(db, appointment_id)
        db.execute(  # someone else commits a change just after we loaded the row
            update(Appointment)
            .where(Appointment.id == appointment_id)
            .values(version=Appointment.version + 1)
            .execution_options(synchronize_session=False)
        )
        db.commit()
        return appointment

    monkeypatch.setattr(booking, "get_appointment", load_then_lose_the_race)

    response = client.patch(f"/appointments/{appt_id}/cancel", json={"reason": "x"})
    assert response.status_code == 409
    assert response.json()["code"] == "concurrent_change"
    assert "Please reload" in response.json()["detail"]
