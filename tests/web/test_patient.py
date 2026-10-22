from datetime import timedelta

from app.models import Appointment
from tests.web.conftest import book_slot, future_monday, sign_in


def start_param(moment):
    return moment.date().isoformat()


def test_a_new_patient_sees_an_empty_state(as_patient):
    page = as_patient.get("/portal/patient")
    assert page.status_code == 200
    assert "Nothing booked yet" in page.text


def test_book_page_lists_doctors_without_times_until_one_is_chosen(as_patient):
    page = as_patient.get("/portal/patient/book")
    assert "Dr. Amina Wanjiru" in page.text
    assert 'class="slot"' not in page.text


def test_book_page_shows_free_times_for_a_doctor_and_day(as_patient):
    monday = future_monday()
    page = as_patient.get(f"/portal/patient/book?doctor_id=1&day={start_param(monday)}")
    assert page.text.count('class="slot"') == 16
    assert "09:00" in page.text


def test_book_page_says_when_a_day_has_no_times(as_patient):
    sunday = future_monday() - timedelta(days=1)
    page = as_patient.get(f"/portal/patient/book?doctor_id=1&day={start_param(sunday)}")
    assert "No free times that day" in page.text


def test_book_page_copes_with_junk_in_the_address(as_patient):
    page = as_patient.get("/portal/patient/book?doctor_id=abc&day=not-a-date")
    assert page.status_code == 200
    page = as_patient.get("/portal/patient/book?doctor_id=999")
    assert "find a doctor" in page.text


def test_booking_a_slot_shows_it_on_the_home_page(as_patient):
    monday = future_monday()
    response = book_slot(as_patient, monday)
    assert response.headers["location"] == "/portal/patient"
    page = as_patient.get("/portal/patient")
    assert "Appointment booked." in page.text
    assert "09:00" in page.text
    assert "Dr. Amina Wanjiru" in page.text
    assert "Reschedule" in page.text


def test_booking_a_taken_slot_explains_and_returns_to_the_times(as_patient, web):
    monday = future_monday()
    book_slot(as_patient, monday)
    response = book_slot(as_patient, monday)
    assert response.headers["location"].startswith("/portal/patient/book?doctor_id=1&day=")
    assert "already booked" in as_patient.get(response.headers["location"]).text


def test_booking_needs_a_real_time(as_patient):
    for data in ({"doctor_id": "1", "start_time": "tomorrow"}, {"doctor_id": "", "start_time": ""}):
        response = as_patient.post("/portal/patient/book", data=data)
        assert response.headers["location"] == "/portal/patient/book"
    assert "pick one of the times" in as_patient.get("/portal/patient/book").text
    # a time with no UTC offset is ambiguous, so it is refused too
    response = as_patient.post(
        "/portal/patient/book", data={"doctor_id": "1", "start_time": "2030-01-07T09:00:00"}
    )
    assert response.headers["location"] == "/portal/patient/book"


def test_cancelling_moves_it_to_history_and_frees_the_slot(as_patient, db):
    monday = future_monday()
    book_slot(as_patient, monday)
    appointment = db.query(Appointment).one()

    response = as_patient.post(
        f"/portal/patient/appointments/{appointment.id}/cancel",
        data={"reason": "Travelling", "version": 1},
    )
    assert response.headers["location"] == "/portal/patient"
    page = as_patient.get("/portal/patient")
    assert "Appointment cancelled." in page.text
    assert "Past and cancelled" in page.text
    assert "Travelling" in page.text
    # the slot can be booked again
    assert book_slot(as_patient, monday).headers["location"] == "/portal/patient"


def test_cancelling_needs_a_reason(as_patient, db):
    book_slot(as_patient, future_monday())
    appointment = db.query(Appointment).one()
    as_patient.post(
        f"/portal/patient/appointments/{appointment.id}/cancel", data={"reason": "  ", "version": 1}
    )
    assert "reason for cancelling" in as_patient.get("/portal/patient").text
    db.refresh(appointment)
    assert appointment.status == "booked"


def test_cancelling_twice_explains_the_problem(as_patient, db):
    book_slot(as_patient, future_monday())
    appointment = db.query(Appointment).one()
    url = f"/portal/patient/appointments/{appointment.id}/cancel"
    as_patient.post(url, data={"reason": "First", "version": 1})
    as_patient.post(url, data={"reason": "Second", "version": 2})  # a fresh page, same appointment
    assert "already cancelled" in as_patient.get("/portal/patient").text


def test_rescheduling_moves_the_appointment(as_patient, db):
    monday = future_monday()
    book_slot(as_patient, monday)
    appointment = db.query(Appointment).one()
    page_url = f"/portal/patient/appointments/{appointment.id}/reschedule"

    page = as_patient.get(page_url)
    assert page.status_code == 200
    assert "Dr. Amina Wanjiru" in page.text
    assert page.text.count('class="slot"') == 15  # its own time is taken

    later = monday.replace(hour=14)
    response = as_patient.post(
        page_url, data={"start_time": later.isoformat(), "version": appointment.version}
    )
    assert response.headers["location"] == "/portal/patient"
    home = as_patient.get("/portal/patient")
    assert "Appointment rescheduled." in home.text
    assert "14:00" in home.text
    assert "Rescheduled" in home.text


def test_reschedule_page_can_look_at_another_day(as_patient, db):
    monday = future_monday()
    book_slot(as_patient, monday)
    appointment = db.query(Appointment).one()
    tuesday = monday + timedelta(days=1)
    page = as_patient.get(
        f"/portal/patient/appointments/{appointment.id}/reschedule?day={start_param(tuesday)}"
    )
    assert page.text.count('class="slot"') == 16
    empty = as_patient.get(
        f"/portal/patient/appointments/{appointment.id}/reschedule"
        f"?day={start_param(monday - timedelta(days=1))}"
    )
    assert "No free times that day" in empty.text


def test_rescheduling_to_a_bad_time_explains_and_changes_nothing(as_patient, db):
    monday = future_monday()
    book_slot(as_patient, monday)
    appointment = db.query(Appointment).one()
    url = f"/portal/patient/appointments/{appointment.id}/reschedule"

    as_patient.post(url, data={"start_time": "soon", "version": 1})
    assert "pick one of the times" in as_patient.get(url).text

    as_patient.post(url, data={"start_time": monday.isoformat(), "version": 1})  # same time
    assert "already at that time" in as_patient.get(url).text
    db.refresh(appointment)
    assert appointment.status == "booked"


def test_a_patient_cannot_touch_someone_elses_appointment(web, db):
    # Demo patient books...
    sign_in(web, "demo@example.com")
    book_slot(web, future_monday())
    appointment = db.query(Appointment).one()
    web.post("/logout")

    # ...a different patient tries to cancel and reschedule it
    web.post(
        "/register", data={"name": "Other", "email": "o@example.com", "password": "longenough"}
    )
    cancel = web.post(
        f"/portal/patient/appointments/{appointment.id}/cancel", data={"reason": "x", "version": 1}
    )
    assert cancel.headers["location"] == "/portal/patient"
    assert "find that appointment" in web.get("/portal/patient").text
    web.get(f"/portal/patient/appointments/{appointment.id}/reschedule")
    web.post(
        f"/portal/patient/appointments/{appointment.id}/reschedule",
        data={"start_time": future_monday(hour=11).isoformat(), "version": 1},
    )
    db.refresh(appointment)
    assert appointment.status == "booked"
    assert appointment.start_time.hour != 8  # still at its original time


def test_rescheduling_an_unknown_appointment_goes_home(as_patient):
    response = as_patient.get("/portal/patient/appointments/999/reschedule")
    assert response.headers["location"] == "/portal/patient"


def test_every_cancel_and_reschedule_form_carries_the_version_it_was_built_from(as_patient, db):
    book_slot(as_patient, future_monday())
    appointment = db.query(Appointment).one()

    home = as_patient.get("/portal/patient")
    assert f'name="version" value="{appointment.version}"' in home.text

    page = as_patient.get(f"/portal/patient/appointments/{appointment.id}/reschedule")
    assert f'name="version" value="{appointment.version}"' in page.text


def test_cancelling_from_an_out_of_date_page_is_refused(as_patient, db):
    monday = future_monday()
    book_slot(as_patient, monday)
    appointment = db.query(Appointment).one()
    seen = appointment.version  # the page the patient has open

    # meanwhile the appointment is moved (for example from another tab)
    url = f"/portal/patient/appointments/{appointment.id}"
    as_patient.post(
        f"{url}/reschedule",
        data={"start_time": monday.replace(hour=14).isoformat(), "version": seen},
    )

    as_patient.post(f"{url}/cancel", data={"reason": "From the old page", "version": seen})

    page = as_patient.get("/portal/patient")
    assert "changed after you opened it" in page.text
    db.refresh(appointment)
    assert appointment.status == "rescheduled"  # not cancelled


def test_rescheduling_from_an_out_of_date_page_is_refused(as_patient, db):
    monday = future_monday()
    book_slot(as_patient, monday)
    appointment = db.query(Appointment).one()
    seen = appointment.version
    url = f"/portal/patient/appointments/{appointment.id}"
    as_patient.post(f"{url}/cancel", data={"reason": "Changed my mind", "version": seen})

    as_patient.post(
        f"{url}/reschedule",
        data={"start_time": monday.replace(hour=14).isoformat(), "version": seen},
    )

    assert "changed after you opened it" in as_patient.get(f"{url}/reschedule").text
    db.refresh(appointment)
    assert appointment.status == "cancelled"


def test_a_form_without_a_version_is_treated_as_out_of_date(as_patient, db):
    monday = future_monday()
    book_slot(as_patient, monday)
    appointment = db.query(Appointment).one()
    url = f"/portal/patient/appointments/{appointment.id}"

    as_patient.post(f"{url}/cancel", data={"reason": "No version sent"})
    assert "out of date" in as_patient.get("/portal/patient").text

    as_patient.post(f"{url}/reschedule", data={"start_time": monday.replace(hour=14).isoformat()})
    assert "out of date" in as_patient.get(f"{url}/reschedule").text

    db.refresh(appointment)
    assert appointment.status == "booked"
