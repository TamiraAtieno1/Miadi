class BookingError(Exception):
    """Base class for expected, user-facing failures.

    Each subclass carries the HTTP status and a stable machine-readable code,
    so the API can return {"detail": "...", "code": "..."} consistently.
    """

    status_code = 400
    code = "booking_error"

    def __init__(self, message: str):
        """Store the human-readable message that is sent back to the client."""
        super().__init__(message)
        self.message = message


class NotFoundError(BookingError):
    """The doctor, patient or appointment does not exist (404)."""

    status_code = 404
    code = "not_found"


class InvalidSlotError(BookingError):
    """The requested time is not a valid bookable slot (422)."""

    status_code = 422
    code = "invalid_slot"


class SlotUnavailableError(BookingError):
    """The slot is valid but already taken (409)."""

    status_code = 409
    code = "slot_unavailable"


class ConcurrentChangeError(BookingError):
    """Someone else changed the same appointment at the same moment (409)."""

    status_code = 409
    code = "concurrent_change"


class InvalidStateError(BookingError):
    """The appointment is in a state that forbids this action (409)."""

    status_code = 409
    code = "invalid_state"


class InvalidCredentialsError(BookingError):
    """The email or password is wrong (401). The message never says which."""

    status_code = 401
    code = "invalid_credentials"


class EmailTakenError(BookingError):
    """An account with this email already exists (409)."""

    status_code = 409
    code = "email_taken"


class InvalidAccountError(BookingError):
    """The sign-up details are not acceptable (422)."""

    status_code = 422
    code = "invalid_account"
