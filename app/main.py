from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app import models  # noqa: F401  (registers tables on Base.metadata)
from app.database import SessionLocal
from app.errors import BookingError
from app.routers import appointments, doctors, patients
from app.seed import seed_if_empty


@asynccontextmanager
async def lifespan(app: FastAPI):
    # The schema is managed by Alembic (`alembic upgrade head`, run by entrypoint.sh).
    with SessionLocal() as db:
        seed_if_empty(db)
    yield


app = FastAPI(
    title="Miadi: Clinic Booking API",
    description="Book, cancel and reschedule 30-minute clinic appointments.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.exception_handler(BookingError)
async def booking_error_handler(request: Request, exc: BookingError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message, "code": exc.code},
    )


app.include_router(doctors.router)
app.include_router(appointments.router)
app.include_router(patients.router)


# Uptime monitors (e.g. UptimeRobot's free plan) probe with HEAD, so allow it as well as GET.
@app.api_route("/health", methods=["GET", "HEAD"], tags=["meta"])
def health() -> dict:
    return {"status": "ok"}
