"""Who is signed in: session handling, role checks and one-time messages."""

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User


class LoginRequired(Exception):
    """Raised when a page needs a signed-in user and there is none."""


class AccessDenied(Exception):
    """Raised when the signed-in user's role may not open the page."""


def sign_in(request: Request, user: User) -> None:
    """Remember the user in the signed session cookie."""
    request.session.clear()
    request.session["user_id"] = user.id


def sign_out(request: Request) -> None:
    """Forget the user."""
    request.session.clear()


def flash(request: Request, message: str, kind: str = "ok") -> None:
    """Queue a message to show on the next page. `kind` is "ok" or "error"."""
    # Assign a new list: the session only notices changes to its own keys,
    # not to a list stored inside it.
    request.session["flashes"] = [*request.session.get("flashes", []), [kind, message]]


def pop_flashes(request: Request) -> list[list[str]]:
    """Take (and clear) the queued messages."""
    return request.session.pop("flashes", [])


def current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    """The signed-in user, or None. A cookie for a deleted account is dropped."""
    user_id = request.session.get("user_id")
    if user_id is None:
        return None
    user = db.get(User, user_id)
    if user is None:
        request.session.clear()
    return user


def require_role(role: str):
    """Build a dependency that only lets users with this role through."""

    def dependency(user: User | None = Depends(current_user)) -> User:
        if user is None:
            raise LoginRequired
        if user.role != role:
            raise AccessDenied
        return user

    return dependency
