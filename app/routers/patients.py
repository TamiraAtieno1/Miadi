from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Patient
from app.schemas import AppointmentOut, PatientCreate, PatientOut
from app.services import booking

router = APIRouter(prefix="/patients", tags=["patients"])


@router.post("", response_model=PatientOut, status_code=201, summary="Create a patient")
def create_patient(body: PatientCreate, db: Session = Depends(get_db)):
    """Create a patient so they can book appointments."""
    patient = Patient(**body.model_dump())
    db.add(patient)
    db.commit()
    db.refresh(patient)
    return patient


@router.get(
    "/{patient_id}/appointments",
    response_model=list[AppointmentOut],
    summary="Upcoming appointments, soonest first",
)
def upcoming_appointments(patient_id: int, db: Session = Depends(get_db)):
    """List a patient's booked appointments that have not started yet."""
    return booking.list_upcoming_for_patient(db, patient_id)
