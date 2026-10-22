import datetime as dt

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_serializer, field_validator

from app.timeutils import to_clinic_time


class WorkingHoursOut(BaseModel):
    """A doctor's working hours on one weekday, in clinic local time."""

    model_config = ConfigDict(from_attributes=True)

    weekday: int  # 0 = Monday ... 6 = Sunday
    start_time: dt.time
    end_time: dt.time


class DoctorOut(BaseModel):
    """A doctor with their weekly working hours."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    specialty: str
    working_hours: list[WorkingHoursOut]


class Slot(BaseModel):
    """One free 30-minute slot."""

    start: dt.datetime
    end: dt.datetime


class AvailabilityOut(BaseModel):
    """The free slots for a doctor on one clinic-local date."""

    doctor_id: int
    date: dt.date
    timezone: str
    slots: list[Slot]


class AppointmentCreate(BaseModel):
    """Request body for booking a slot."""

    doctor_id: int
    patient_id: int
    # AwareDatetime rejects timestamps without an offset, so there is no
    # ambiguity about which timezone the client meant.
    start_time: AwareDatetime


EXPECTED_VERSION = Field(
    ge=1,
    description=(
        "The `version` of the appointment as you last saw it. If someone has changed the "
        "appointment since, the request is refused with 409 `stale_version`."
    ),
)


class CancelRequest(BaseModel):
    """Request body for cancelling an appointment. A reason and the version you saw are required."""

    model_config = ConfigDict(str_strip_whitespace=True)

    reason: str = Field(min_length=1, max_length=500)
    expected_version: int = EXPECTED_VERSION


class RescheduleRequest(BaseModel):
    """Request body for moving an appointment: the new start time and the version you saw."""

    start_time: AwareDatetime
    expected_version: int = EXPECTED_VERSION


class AppointmentOut(BaseModel):
    """An appointment as returned by the API, with times in clinic local time."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    doctor_id: int
    patient_id: int
    start_time: dt.datetime
    end_time: dt.datetime
    status: str
    version: int  # send this back as `expected_version` when you cancel or reschedule
    cancel_reason: str | None
    cancelled_at: dt.datetime | None
    created_at: dt.datetime
    updated_at: dt.datetime

    # Stored in UTC, returned in clinic local time (+03:00) so the response
    # matches the timestamps clients send and the working hours they see.
    @field_serializer("start_time", "end_time", "created_at", "updated_at")
    def _to_clinic_time(self, value: dt.datetime) -> dt.datetime:
        """Serialise a stored UTC timestamp as clinic local time."""
        return to_clinic_time(value)

    @field_serializer("cancelled_at")
    def _to_clinic_time_optional(self, value: dt.datetime | None) -> dt.datetime | None:
        """Same as above for the optional `cancelled_at` timestamp."""
        return to_clinic_time(value) if value else None


class PatientCreate(BaseModel):
    """Request body for creating a patient."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=100)
    phone: str | None = Field(default=None, max_length=30)
    email: str | None = Field(default=None, max_length=255)

    @field_validator("email")
    @classmethod
    def _normalise_email(cls, value: str | None) -> str | None:
        """Store emails in lower case, and treat a blank one as "no email"."""
        value = (value or "").strip().lower()
        return value or None


class PatientOut(BaseModel):
    """A patient as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    phone: str | None
    email: str | None
