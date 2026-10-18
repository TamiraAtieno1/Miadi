from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import models  # noqa: F401  (registers tables on Base.metadata)
from app.database import Base, SessionLocal, engine
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


@app.get("/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok"}
