from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import AppointmentOut, PatientCreate, PatientOut
from app.services import availability, patients

router = APIRouter(prefix="/patients", tags=["patients"])


@router.post("", response_model=PatientOut, status_code=201, summary="Create a patient")
def create_patient(body: PatientCreate, db: Session = Depends(get_db)):
    """Create a patient so they can book appointments. Returns 409 if the email is already used."""
    return patients.create_patient(db, body.name, body.phone, body.email)


@router.get(
    "/{patient_id}/appointments",
    response_model=list[AppointmentOut],
    summary="Upcoming appointments, soonest first",
)
def upcoming_appointments(patient_id: int, db: Session = Depends(get_db)):
    """List a patient's booked appointments that have not started yet."""
    return availability.list_upcoming_for_patient(db, patient_id)
