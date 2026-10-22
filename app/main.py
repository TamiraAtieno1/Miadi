from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app import models  # noqa: F401  (registers tables on Base.metadata)
from app.errors import BookingError
from app.routers import appointments, doctors, patients
from app.validation import describe_errors

app = FastAPI(
    title="Miadi: Clinic Booking API",
    description="Book, cancel and reschedule 30-minute clinic appointments.",
    version="0.1.0",
)


@app.exception_handler(BookingError)
async def booking_error_handler(request: Request, exc: BookingError) -> JSONResponse:
    """Turn an expected booking failure into a JSON error with its HTTP status and code."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message, "code": exc.code},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Answer bad input with one plain sentence in the same shape as other errors."""
    return JSONResponse(
        status_code=422,
        content={"detail": describe_errors(exc.errors()), "code": "validation_error"},
    )


app.include_router(doctors.router)
app.include_router(appointments.router)
app.include_router(patients.router)


# Uptime monitors (e.g. UptimeRobot's free plan) probe with HEAD, so allow it as well as GET.
@app.api_route("/health", methods=["GET", "HEAD"], tags=["meta"])
def health() -> dict:
    """Liveness check used by Render and uptime monitors."""
    return {"status": "ok"}
