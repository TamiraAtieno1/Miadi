from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import (
    AppointmentCreate,
    AppointmentOut,
    CancelRequest,
    RescheduleRequest,
)
from app.services import booking

router = APIRouter(prefix="/appointments", tags=["appointments"])


@router.post(
    "",
    response_model=AppointmentOut,
    status_code=201,
    summary="Book a slot",
)
def create_appointment(body: AppointmentCreate, db: Session = Depends(get_db)):
    """Book a 30-minute slot. Returns 409 if it is taken and 422 if it is not a valid slot."""
    return booking.book_appointment(db, body.doctor_id, body.patient_id, body.start_time)


@router.patch(
    "/{appointment_id}/cancel",
    response_model=AppointmentOut,
    summary="Cancel an appointment (the slot becomes bookable again)",
)
def cancel_appointment(appointment_id: int, body: CancelRequest, db: Session = Depends(get_db)):
    """Cancel an appointment with a reason, freeing its slot. 409 if its version is out of date."""
    return booking.cancel_appointment(db, appointment_id, body.reason, body.expected_version)


@router.patch(
    "/{appointment_id}/reschedule",
    response_model=AppointmentOut,
    summary="Move an appointment to a new slot",
)
def reschedule_appointment(
    appointment_id: int, body: RescheduleRequest, db: Session = Depends(get_db)
):
    """Move an appointment to a new slot with the same doctor. 409 if its version is out of date."""
    return booking.reschedule_appointment(
        db, appointment_id, body.start_time, body.expected_version
    )
