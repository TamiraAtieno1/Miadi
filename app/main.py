import os
import secrets

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app import models  # noqa: F401  (registers tables on Base.metadata)
from app.errors import BookingError
from app.routers import appointments, doctors, patients
from app.validation import describe_errors
from app.web import routes as web_routes
from app.web.auth import AccessDenied, LoginRequired, flash
from app.web.templating import BASE_DIR, render

app = FastAPI(
    title="Miadi: Clinic Booking API",
    description="Book, cancel and reschedule 30-minute clinic appointments.",
    version="0.1.0",
)


# Sessions are a signed cookie. Set SECRET_KEY in production: without it a random key is
# made at start-up and everyone is signed out whenever the app restarts.
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SECRET_KEY") or secrets.token_urlsafe(32),
    max_age=60 * 60 * 8,
    same_site="lax",
    https_only=os.environ.get("SECURE_COOKIES") == "1",
)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


@app.exception_handler(LoginRequired)
async def login_required_handler(request: Request, exc: LoginRequired) -> RedirectResponse:
    """Send visitors who aren't signed in to the sign-in page."""
    flash(request, "Please sign in to continue.", "error")
    return RedirectResponse("/login", status_code=303)


@app.exception_handler(AccessDenied)
async def access_denied_handler(request: Request, exc: AccessDenied):
    """Show a plain "not for you" page when a role opens another role's page."""
    return render(
        request,
        "error.html",
        status_code=403,
        message="That page is for a different kind of account.",
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
app.include_router(web_routes.router)


# Uptime monitors (e.g. UptimeRobot's free plan) probe with HEAD, so allow it as well as GET.
@app.api_route("/health", methods=["GET", "HEAD"], tags=["meta"])
def health() -> dict:
    """Liveness check used by Render and uptime monitors."""
    return {"status": "ok"}
