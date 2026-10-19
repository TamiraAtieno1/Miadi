from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Doctor
from app.schemas import AvailabilityOut, DoctorOut, Slot
from app.services import booking
from app.timeutils import CLINIC_TZ

router = APIRouter(prefix="/doctors", tags=["doctors"])


@router.get("", response_model=list[DoctorOut], summary="List doctors")
def list_doctors(db: Session = Depends(get_db)):
    return db.scalars(select(Doctor).order_by(Doctor.id)).all()


@router.get(
    "/{doctor_id}/availability",
    response_model=AvailabilityOut,
    summary="Free 30-minute slots for a doctor on a date",
)
def doctor_availability(
    doctor_id: int,
    day: date = Query(..., alias="date", description="Clinic-local date, YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    slots = booking.get_availability(db, doctor_id, day)
    return AvailabilityOut(
        doctor_id=doctor_id,
        date=day,
        timezone=str(CLINIC_TZ),
        slots=[Slot(start=start, end=end) for start, end in slots],
    )
