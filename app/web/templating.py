"""Jinja2 setup: clinic-time formatting and the shared page context."""

from datetime import datetime
from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates

from app.models import ACTIVE_STATUSES, STATUS_CANCELLED, STATUS_RESCHEDULED
from app.timeutils import as_utc, to_clinic_time, utcnow
from app.web.auth import pop_flashes

BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

STATUS_LABELS = {
    "booked": "Booked",
    STATUS_RESCHEDULED: "Rescheduled",
    STATUS_CANCELLED: "Cancelled",
}


def clock(value: datetime) -> str:
    """09:30 in clinic time."""
    return to_clinic_time(value).strftime("%H:%M")


def day_name(value) -> str:
    """Mon 26 Oct. Accepts a datetime (shown in clinic time) or a date."""
    if isinstance(value, datetime):
        value = to_clinic_time(value)
    return f"{value:%a} {value.day} {value:%b}"


def is_open(appointment, now: datetime) -> bool:
    """True while an appointment can still be cancelled or rescheduled."""
    return appointment.status in ACTIVE_STATUSES and as_utc(appointment.start_time) > now


templates.env.filters["clock"] = clock
templates.env.filters["day_name"] = day_name
templates.env.globals["is_open"] = is_open
templates.env.globals["status_label"] = lambda status: STATUS_LABELS.get(status, status)


def render(request: Request, name: str, user=None, status_code: int = 200, **context):
    """Render a page with the signed-in user, queued messages and the current time."""
    context.update(user=user, flashes=pop_flashes(request), now=utcnow())
    return templates.TemplateResponse(request, name, context, status_code=status_code)
