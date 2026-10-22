"""The HTML pages. Every page is a thin wrapper over the same services the JSON API uses."""

import os
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.errors import BookingError, NotFoundError
from app.models import (
    ROLE_ADMIN,
    ROLE_DOCTOR,
    ROLE_PATIENT,
    STATUS_BOOKED,
    STATUS_CANCELLED,
    STATUS_RESCHEDULED,
    Appointment,
    Doctor,
    User,
)
from app.seed import ADMIN_EMAIL, DEFAULT_DEMO_PASSWORD, demo_password, doctor_email
from app.services import accounts, availability, booking, schedule
from app.services.lookups import get_appointment
from app.timeutils import to_clinic_time, utcnow
from app.web.auth import current_user, flash, require_role, sign_in, sign_out
from app.web.templating import render

router = APIRouter(include_in_schema=False)

HOME = {
    ROLE_PATIENT: "/portal/patient",
    ROLE_DOCTOR: "/portal/doctor",
    ROLE_ADMIN: "/portal/admin",
}
# Reused as route defaults (a call inside a default argument would trip lint rule B008).
as_patient = Depends(require_role(ROLE_PATIENT))
as_doctor = Depends(require_role(ROLE_DOCTOR))
as_admin = Depends(require_role(ROLE_ADMIN))
STATUS_CHOICES = (STATUS_BOOKED, STATUS_RESCHEDULED, STATUS_CANCELLED)


def go(url: str) -> RedirectResponse:
    """Redirect after a form post (303 makes the browser follow with GET)."""
    return RedirectResponse(url, status_code=303)


def clinic_today() -> date:
    """Today's date at the clinic."""
    return to_clinic_time(utcnow()).date()


def parse_day(value: str | None) -> date:
    """Read YYYY-MM-DD from a form, falling back to today when it is missing or wrong."""
    try:
        return date.fromisoformat(value or "")
    except ValueError:
        return clinic_today()


def parse_id(value: str | None) -> int | None:
    """Read a whole number from a form, or None."""
    return int(value) if value and value.isdigit() else None


def parse_start(value: str | None) -> datetime | None:
    """Read a slot's start (ISO 8601 with a UTC offset) from a form, or None."""
    try:
        start = datetime.fromisoformat(value or "")
    except ValueError:
        return None
    return start if start.tzinfo else None


def group_by_day(appointments: list[Appointment]) -> list[tuple[date, list[Appointment]]]:
    """Group a start-time-ordered list by clinic-local date."""
    days: dict[date, list[Appointment]] = {}
    for appointment in appointments:
        days.setdefault(to_clinic_time(appointment.start_time).date(), []).append(appointment)
    return list(days.items())


def own_appointment(db: Session, user: User, appointment_id: int) -> Appointment:
    """Load an appointment the user may change, or raise "not found".

    A patient only sees their own, a doctor only theirs and an admin any. Someone
    else's appointment gets the same answer as one that doesn't exist.
    """
    missing = NotFoundError("We couldn't find that appointment.")
    try:
        appointment = get_appointment(db, appointment_id)
    except NotFoundError:
        raise missing from None
    allowed = (
        user.role == ROLE_ADMIN
        or (user.role == ROLE_PATIENT and appointment.patient_id == user.patient_id)
        or (user.role == ROLE_DOCTOR and appointment.doctor_id == user.doctor_id)
    )
    if not allowed:
        raise missing
    return appointment


# ---------------------------------------------------------------- sign in / out


@router.get("/")
def index(user: User | None = Depends(current_user)):
    """Send visitors to their home page, or to sign in."""
    return go(HOME[user.role] if user else "/login")


@router.get("/login")
def login_page(request: Request, user: User | None = Depends(current_user)):
    """Show the sign-in form."""
    if user:
        return go(HOME[user.role])
    show_demo = os.environ.get("SHOW_DEMO_LOGINS", "1") != "0"
    return render(
        request,
        "login.html",
        demo=show_demo,
        demo_password=demo_password() if show_demo else None,
        demo_accounts=[
            ("Patient", "demo@example.com"),
            ("Doctor", doctor_email("Dr. Amina Wanjiru")),
            ("Admin", ADMIN_EMAIL),
        ],
        default_password=DEFAULT_DEMO_PASSWORD,
    )


@router.post("/login")
def login(
    request: Request,
    email: str = Form(""),
    password: str = Form(""),
    db: Session = Depends(get_db),
):
    """Check the email and password and open the right home page."""
    try:
        user = accounts.authenticate(db, email, password)
    except BookingError as error:
        flash(request, error.message, "error")
        return go("/login")
    sign_in(request, user)
    return go(HOME[user.role])


@router.post("/logout")
def logout(request: Request):
    """Sign out."""
    sign_out(request)
    flash(request, "You're signed out.")
    return go("/login")


@router.get("/register")
def register_page(request: Request, user: User | None = Depends(current_user)):
    """Show the patient sign-up form."""
    if user:
        return go(HOME[user.role])
    return render(request, "register.html")


@router.post("/register")
def register(
    request: Request,
    name: str = Form(""),
    email: str = Form(""),
    password: str = Form(""),
    db: Session = Depends(get_db),
):
    """Create a patient account and sign the new patient in."""
    try:
        user = accounts.register_patient(db, name, email, password)
    except BookingError as error:
        flash(request, error.message, "error")
        return go("/register")
    sign_in(request, user)
    flash(request, "Welcome to Miadi. Your account is ready.")
    return go(HOME[user.role])


# --------------------------------------------------------------------- patient


@router.get("/portal/patient")
def patient_home(
    request: Request,
    user: User = as_patient,
    db: Session = Depends(get_db),
):
    """A patient's upcoming appointments and history."""
    upcoming, history = schedule.patient_appointments(db, user.patient_id)
    return render(
        request, "patient/home.html", user, upcoming=group_by_day(upcoming), history=history
    )


@router.get("/portal/patient/book")
def book_page(
    request: Request,
    doctor_id: str | None = None,
    day: str | None = None,
    user: User = as_patient,
    db: Session = Depends(get_db),
):
    """Pick a doctor and a day, then a free time."""
    doctors = list(db.scalars(select(Doctor).order_by(Doctor.name)))
    chosen = parse_id(doctor_id)
    chosen_day = parse_day(day)
    slots = None
    if chosen is not None:
        try:
            slots = availability.get_availability(db, chosen, chosen_day)
        except BookingError as error:
            flash(request, error.message, "error")
    return render(
        request,
        "patient/book.html",
        user,
        doctors=doctors,
        doctor_id=chosen,
        day=chosen_day,
        today=clinic_today(),
        last_day=clinic_today() + timedelta(days=90),
        slots=slots,
    )


@router.post("/portal/patient/book")
def book(
    request: Request,
    doctor_id: str = Form(""),
    start_time: str = Form(""),
    user: User = as_patient,
    db: Session = Depends(get_db),
):
    """Book the chosen slot."""
    doctor = parse_id(doctor_id)
    start = parse_start(start_time)
    if doctor is None or start is None:
        flash(request, "Please pick one of the times shown.", "error")
        return go("/portal/patient/book")
    try:
        booking.book_appointment(db, doctor, user.patient_id, start)
    except BookingError as error:
        flash(request, error.message, "error")
        return go(f"/portal/patient/book?doctor_id={doctor}&day={to_clinic_time(start).date()}")
    flash(request, "Appointment booked.")
    return go("/portal/patient")


@router.get("/portal/patient/appointments/{appointment_id}/reschedule")
def reschedule_page(
    request: Request,
    appointment_id: int,
    day: str | None = None,
    user: User = as_patient,
    db: Session = Depends(get_db),
):
    """Pick a new time with the same doctor."""
    try:
        appointment = own_appointment(db, user, appointment_id)
    except BookingError as error:
        flash(request, error.message, "error")
        return go("/portal/patient")
    chosen_day = parse_day(day)
    if day is None:
        chosen_day = max(clinic_today(), to_clinic_time(appointment.start_time).date())
    slots = availability.get_availability(db, appointment.doctor_id, chosen_day)
    return render(
        request,
        "patient/reschedule.html",
        user,
        appointment=appointment,
        day=chosen_day,
        today=clinic_today(),
        last_day=clinic_today() + timedelta(days=90),
        slots=slots,
    )


@router.post("/portal/patient/appointments/{appointment_id}/reschedule")
def reschedule(
    request: Request,
    appointment_id: int,
    start_time: str = Form(""),
    user: User = as_patient,
    db: Session = Depends(get_db),
):
    """Move the appointment to the chosen slot."""
    back = f"/portal/patient/appointments/{appointment_id}/reschedule"
    start = parse_start(start_time)
    if start is None:
        flash(request, "Please pick one of the times shown.", "error")
        return go(back)
    try:
        appointment = own_appointment(db, user, appointment_id)
        booking.reschedule_appointment(db, appointment.id, start)
    except BookingError as error:
        flash(request, error.message, "error")
        return go(back)
    flash(request, "Appointment rescheduled.")
    return go("/portal/patient")


def cancel_for(
    request: Request, db: Session, user: User, appointment_id: int, reason: str, back: str
) -> RedirectResponse:
    """Cancel an appointment the user is allowed to change, then return to `back`."""
    try:
        appointment = own_appointment(db, user, appointment_id)
        reason = reason.strip()
        if not reason:
            flash(request, "Please give a reason for cancelling.", "error")
            return go(back)
        booking.cancel_appointment(db, appointment.id, reason[:500])
    except BookingError as error:
        flash(request, error.message, "error")
        return go(back)
    flash(request, "Appointment cancelled.")
    return go(back)


@router.post("/portal/patient/appointments/{appointment_id}/cancel")
def patient_cancel(
    request: Request,
    appointment_id: int,
    reason: str = Form(""),
    user: User = as_patient,
    db: Session = Depends(get_db),
):
    """A patient cancels one of their own appointments."""
    return cancel_for(request, db, user, appointment_id, reason, "/portal/patient")


# ---------------------------------------------------------------------- doctor


@router.get("/portal/doctor")
def doctor_home(
    request: Request,
    user: User = as_doctor,
    db: Session = Depends(get_db),
):
    """A doctor's upcoming appointments, by day."""
    upcoming = schedule.doctor_appointments(db, user.doctor_id)
    return render(request, "doctor/home.html", user, days=group_by_day(upcoming))


@router.post("/portal/doctor/appointments/{appointment_id}/cancel")
def doctor_cancel(
    request: Request,
    appointment_id: int,
    reason: str = Form(""),
    user: User = as_doctor,
    db: Session = Depends(get_db),
):
    """A doctor cancels one of their own appointments."""
    return cancel_for(request, db, user, appointment_id, reason, "/portal/doctor")


# ----------------------------------------------------------------------- admin


@router.get("/portal/admin")
def admin_home(
    request: Request,
    status: str | None = None,
    user: User = as_admin,
    db: Session = Depends(get_db),
):
    """Every appointment in the clinic, with a status filter and headline numbers."""
    status = status if status in STATUS_CHOICES else None
    return render(
        request,
        "admin/home.html",
        user,
        appointments=schedule.all_appointments(db, status),
        counts=schedule.appointment_counts(db),
        status=status,
        statuses=STATUS_CHOICES,
        doctors=list(db.scalars(select(Doctor).order_by(Doctor.name))),
    )


@router.post("/portal/admin/appointments/{appointment_id}/cancel")
def admin_cancel(
    request: Request,
    appointment_id: int,
    reason: str = Form(""),
    user: User = as_admin,
    db: Session = Depends(get_db),
):
    """An admin cancels any appointment."""
    return cancel_for(request, db, user, appointment_id, reason, "/portal/admin")
