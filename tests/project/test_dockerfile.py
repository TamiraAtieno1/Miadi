"""The container must not run the app as root."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def instructions() -> list[tuple[str, str]]:
    """(INSTRUCTION, arguments) for each line of the Dockerfile, skipping comments."""
    rows = []
    for line in (ROOT / "Dockerfile").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            keyword, _, rest = line.partition(" ")
            rows.append((keyword.upper(), rest))
    return rows


def test_the_container_switches_to_a_non_root_user():
    users = [rest.strip() for keyword, rest in instructions() if keyword == "USER"]
    assert users, "the Dockerfile never sets USER, so the app would run as root"
    assert users[-1] not in ("root", "0", "0:0"), "the last USER must not be root"


def test_the_user_is_set_before_the_start_command():
    keywords = [keyword for keyword, _ in instructions()]
    assert keywords.index("USER") < keywords.index("CMD")


def test_the_non_root_user_is_created_in_the_image():
    created = [rest for keyword, rest in instructions() if keyword == "RUN" and "useradd" in rest]
    assert created
    assert "appuser" in created[0]
