from datetime import UTC, datetime, time

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

STATUS_BOOKED = "booked"
STATUS_RESCHEDULED = "rescheduled"
STATUS_CANCELLED = "cancelled"

# Statuses that hold a slot. A cancelled appointment does not.
ACTIVE_STATUSES = (STATUS_BOOKED, STATUS_RESCHEDULED)


def _utcnow() -> datetime:
    """Current time in UTC, used as the default for timestamp columns."""
    return datetime.now(UTC)


class Doctor(Base):
    """A clinic doctor. Their weekly schedule is stored in `WorkingHours`."""

    __tablename__ = "doctors"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    specialty: Mapped[str] = mapped_column(String(100), default="General Practice")

    working_hours: Mapped[list["WorkingHours"]] = relationship(back_populates="doctor")


class WorkingHours(Base):
    """One row per doctor per working weekday (0 = Monday ... 6 = Sunday).

    Times are in the clinic's local timezone (Africa/Nairobi).
    A weekday with no row means the doctor does not work that day.
    """

    __tablename__ = "working_hours"
    __table_args__ = (UniqueConstraint("doctor_id", "weekday", name="uq_doctor_weekday"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctors.id"))
    weekday: Mapped[int] = mapped_column(SmallInteger)
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)

    doctor: Mapped[Doctor] = relationship(back_populates="working_hours")


class Patient(Base):
    """A person who books appointments. There is no authentication in this scope."""

    __tablename__ = "patients"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)


class Appointment(Base):
    """A 30-minute booking of a doctor by a patient.

    Times are stored in UTC. Status is `booked`, then `rescheduled` once it has
    been moved to a new slot, or `cancelled`. Cancelling is a soft delete: the
    row stays with a reason and a timestamp.
    """

    __tablename__ = "appointments"
    __table_args__ = (
        # The core concurrency guarantee: at most ONE active appointment (booked
        # or rescheduled) per doctor per start time. Cancelled rows are
        # excluded, so a cancelled slot becomes bookable again with no extra logic.
        Index(
            "uq_active_slot",
            "doctor_id",
            "start_time",
            unique=True,
            postgresql_where=text("status IN ('booked', 'rescheduled')"),
            sqlite_where=text("status IN ('booked', 'rescheduled')"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctors.id"), index=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default=STATUS_BOOKED)
    cancel_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
    # Optimistic concurrency: every UPDATE is "... WHERE version = <the version I read>"
    # and bumps it. If someone else changed the row first, nothing matches and
    # SQLAlchemy raises StaleDataError instead of silently overwriting their change.
    version: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"))

    __mapper_args__ = {"version_id_col": version}
