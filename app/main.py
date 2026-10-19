from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app import models  # noqa: F401  (registers tables on Base.metadata)
from app.database import Base, SessionLocal, engine
from app.errors import BookingError
from app.routers import appointments, doctors, patients
from app.seed import seed_if_empty


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Simple for this scope; a real deployment would use Alembic migrations.
    Base.metadata.create_all(bind=engine)
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


@app.get("/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok"}
