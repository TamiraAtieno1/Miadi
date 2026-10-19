import datetime as dt

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_serializer

from app.timeutils import to_clinic_time


class WorkingHoursOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    weekday: int  # 0 = Monday ... 6 = Sunday
    start_time: dt.time
    end_time: dt.time


class DoctorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    specialty: str
    working_hours: list[WorkingHoursOut]


class Slot(BaseModel):
    start: dt.datetime
    end: dt.datetime


class AvailabilityOut(BaseModel):
    doctor_id: int
    date: dt.date
    timezone: str
    slots: list[Slot]


class AppointmentCreate(BaseModel):
    doctor_id: int
    patient_id: int
    # AwareDatetime rejects timestamps without an offset, so there is no
    # ambiguity about which timezone the client meant.
    start_time: AwareDatetime


class CancelRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    reason: str = Field(min_length=1, max_length=500)


class RescheduleRequest(BaseModel):
    start_time: AwareDatetime


class AppointmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    doctor_id: int
    patient_id: int
    start_time: dt.datetime
    end_time: dt.datetime
    status: str
    cancel_reason: str | None
    cancelled_at: dt.datetime | None
    created_at: dt.datetime
    updated_at: dt.datetime

    # Stored in UTC, returned in clinic local time (+03:00) so the response
    # matches the timestamps clients send and the working hours they see.
    @field_serializer("start_time", "end_time", "created_at", "updated_at")
    def _to_clinic_time(self, value: dt.datetime) -> dt.datetime:
        return to_clinic_time(value)

    @field_serializer("cancelled_at")
    def _to_clinic_time_optional(self, value: dt.datetime | None) -> dt.datetime | None:
        return to_clinic_time(value) if value else None


class PatientCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=100)
    phone: str | None = Field(default=None, max_length=30)
    email: str | None = Field(default=None, max_length=255)


class PatientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    phone: str | None
    email: str | None
