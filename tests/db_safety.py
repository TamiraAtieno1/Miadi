"""Refuse to run the tests against a database that holds real data.

The test fixtures drop and re-create every table, which would wipe a developer's,
staging or production database if DATABASE_URL happened to point at one.
"""

from sqlalchemy.engine import make_url

IN_MEMORY = ("", ":memory:")


def assert_safe_test_database(url: str) -> None:
    """Raise ValueError unless `url` is clearly a throw-away test database.

    Allowed: in-memory SQLite, a SQLite file with "test" in its name, or a
    PostgreSQL database whose name ends in "_test" (CI uses clinic_test).
    """
    try:
        parsed = make_url(url)
    except Exception as error:
        raise ValueError(f"DATABASE_URL is not a valid database URL: {error}") from error

    backend = parsed.get_backend_name()
    database = parsed.database or ""

    if backend == "sqlite":
        # Judge the file name only: a folder called "pytest-of-..." must not count.
        filename = database.replace("\\", "/").rsplit("/", 1)[-1]
        if database in IN_MEMORY or "test" in filename.lower():
            return
    elif backend == "postgresql":
        if database.lower().endswith("_test"):
            return

    shown = parsed.render_as_string(hide_password=True)
    raise ValueError(
        f"Refusing to run the tests against {shown}.\n"
        "The tests drop and re-create every table, so they only run against a database "
        "that is clearly for testing: in-memory SQLite (the default), a SQLite file with "
        "'test' in its name, or a PostgreSQL database whose name ends in '_test'.\n"
        "Unset DATABASE_URL to use the default, or point it at a test database."
    )
