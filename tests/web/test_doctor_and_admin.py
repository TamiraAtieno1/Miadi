from app.models import Appointment
from tests.web.conftest import (
    ADMIN_EMAIL,
    DOCTOR_ONE,
    DOCTOR_TWO,
    book_slot,
    future_monday,
    sign_in,
)


def book_as_demo_patient(web, start, doctor_id=1):
    sign_in(web, "demo@example.com")
    book_slot(web, start, doctor_id)
    web.post("/logout")


def test_a_doctor_with_no_bookings_sees_an_empty_state(as_doctor):
    page = as_doctor.get("/portal/doctor")
    assert page.status_code == 200
    assert "Dr. Amina Wanjiru" in page.text
    assert "No upcoming appointments" in page.text


def test_a_doctor_sees_their_patients_by_day(web):
    book_as_demo_patient(web, future_monday())
    sign_in(web, "amina.wanjiru@example.com")
    page = web.get("/portal/doctor")
    assert "Demo Patient" in page.text
    assert "09:00" in page.text


def test_a_doctor_does_not_see_another_doctors_patients(web):
    book_as_demo_patient(web, future_monday(), doctor_id=2)
    sign_in(web, "amina.wanjiru@example.com")
    assert "Demo Patient" not in web.get("/portal/doctor").text


def test_a_doctor_can_cancel_their_own_appointment(web, db):
    book_as_demo_patient(web, future_monday())
    sign_in(web, "amina.wanjiru@example.com")
    appointment = db.query(Appointment).one()

    response = web.post(
        f"/portal/doctor/appointments/{appointment.id}/cancel",
        data={"reason": "Called to theatre", "version": 1},
    )
    assert response.headers["location"] == "/portal/doctor"
    assert "Appointment cancelled." in web.get("/portal/doctor").text
    db.refresh(appointment)
    assert appointment.status == "cancelled"
    assert appointment.cancel_reason == "Called to theatre"


def test_a_doctor_cannot_cancel_another_doctors_appointment(web, db):
    book_as_demo_patient(web, future_monday())
    sign_in(web, DOCTOR_TWO)
    appointment = db.query(Appointment).one()

    web.post(
        f"/portal/doctor/appointments/{appointment.id}/cancel", data={"reason": "x", "version": 1}
    )
    assert "find that appointment" in web.get("/portal/doctor").text
    db.refresh(appointment)
    assert appointment.status == "booked"


def test_admin_overview_shows_counts_doctors_and_appointments(web):
    book_as_demo_patient(web, future_monday())
    sign_in(web, ADMIN_EMAIL)
    page = web.get("/portal/admin")
    assert page.status_code == 200
    assert "Dr. Esther Njeri" in page.text
    assert "Demo Patient" in page.text
    assert "Upcoming" in page.text


def test_admin_can_filter_by_status(web, db):
    book_as_demo_patient(web, future_monday())
    sign_in(web, ADMIN_EMAIL)
    assert "Demo Patient" in web.get("/portal/admin?status=booked").text
    cancelled = web.get("/portal/admin?status=cancelled")
    assert "Demo Patient" not in cancelled.text
    assert "No appointments match" in cancelled.text
    assert web.get("/portal/admin?status=nonsense").status_code == 200


def test_admin_can_cancel_any_appointment(web, db):
    book_as_demo_patient(web, future_monday())
    sign_in(web, ADMIN_EMAIL)
    appointment = db.query(Appointment).one()

    response = web.post(
        f"/portal/admin/appointments/{appointment.id}/cancel",
        data={"reason": "Clinic closed", "version": 1},
    )
    assert response.headers["location"] == "/portal/admin"
    assert "Cancelled" in web.get("/portal/admin?status=cancelled").text
    db.refresh(appointment)
    assert appointment.cancel_reason == "Clinic closed"


def test_cancelling_an_unknown_appointment_explains(web):
    sign_in(web, ADMIN_EMAIL)
    web.post("/portal/admin/appointments/999/cancel", data={"reason": "x", "version": 1})
    assert "find that appointment" in web.get("/portal/admin").text


def test_doctor_and_admin_forms_also_refuse_an_out_of_date_page(web, db):
    book_as_demo_patient(web, future_monday())
    appointment = db.query(Appointment).one()
    for email, role in ((DOCTOR_ONE, "doctor"), (ADMIN_EMAIL, "admin")):
        sign_in(web, email)
        web.post(
            f"/portal/{role}/appointments/{appointment.id}/cancel",
            data={"reason": "Old page", "version": appointment.version + 1},
        )
        web.get(f"/portal/{role}")  # shows the message
        db.refresh(appointment)
        assert appointment.status == "booked"
        web.post("/logout")


def test_doctor_and_admin_pages_put_the_version_in_the_cancel_form(web, db):
    book_as_demo_patient(web, future_monday())
    appointment = db.query(Appointment).one()
    sign_in(web, DOCTOR_ONE)
    assert f'name="version" value="{appointment.version}"' in web.get("/portal/doctor").text
    web.post("/logout")
    sign_in(web, ADMIN_EMAIL)
    assert f'name="version" value="{appointment.version}"' in web.get("/portal/admin").text
