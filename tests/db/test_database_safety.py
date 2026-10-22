import os
import subprocess
import sys

import pytest

from tests.db_safety import assert_safe_test_database


@pytest.mark.parametrize(
    "url",
    [
        "sqlite://",
        "sqlite:///:memory:",
        "sqlite:///./test.db",
        "sqlite:///C:/work/clinic_test.db",
        "postgresql://postgres:pw@localhost:5432/clinic_test",
        "postgresql+psycopg2://postgres:pw@localhost/miadi_test",
        "postgres://u:p@db.example.com/anything_TEST",
    ],
)
def test_throwaway_databases_are_allowed(url):
    assert_safe_test_database(url.replace("postgres://", "postgresql://"))


@pytest.mark.parametrize(
    "url",
    [
        "sqlite:///./clinic.db",
        "sqlite:////var/data/clinic.db",
        "postgresql://postgres:secret@localhost:5432/clinic",
        "postgresql://u:secret@dpg-abc.render.com/miadi_prod",
        "mysql://u:p@localhost/clinic_test",
    ],
)
def test_real_looking_databases_are_refused(url):
    with pytest.raises(ValueError, match="Refusing to run the tests") as refused:
        assert_safe_test_database(url)
    assert "secret" not in str(refused.value)  # never print the password


def test_a_malformed_url_is_refused():
    with pytest.raises(ValueError, match="not a valid database URL"):
        assert_safe_test_database("not a url")


def test_pytest_stops_before_touching_an_unsafe_database(tmp_path):
    """Run a real pytest with DATABASE_URL pointing at a "real" file: it must exit at once."""
    real = tmp_path / "clinic.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{real}"}
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/services", "-q", "-p", "no:cacheprovider"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0  # pytest reports a conftest failure as a usage error
    assert "Refusing to run the tests" in result.stdout + result.stderr
    assert not real.exists()  # nothing was created or dropped
