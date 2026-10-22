"""pyproject.toml lists the dependencies; requirements/ locks the exact versions."""

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCKS = ROOT / "requirements"


def _name(requirement: str) -> str:
    """The normalised package name from a requirement like 'psycopg2-binary>=2.9'."""
    return re.split(r"[<>=!~\[; ]", requirement, maxsplit=1)[0].lower().replace("_", "-")


def _pinned(name: str) -> dict[str, str]:
    """package name -> exact version, for every `name==version` line in a lock file."""
    pins = {}
    for line in (LOCKS / name).read_text().splitlines():
        match = re.match(r"^([A-Za-z0-9_.\-]+)==([^\s;]+)", line)
        if match:
            pins[match.group(1).lower().replace("_", "-")] = match.group(2)
    return pins


def _pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]


def test_no_requirements_files_are_left_outside_the_requirements_folder():
    stray = [p.name for p in ROOT.glob("requirements*.txt")]
    assert stray == []


def test_base_lock_pins_every_runtime_dependency():
    pins = _pinned("base.txt")
    for requirement in _pyproject()["dependencies"]:
        assert _name(requirement) in pins, f"{requirement} is not locked in requirements/base.txt"


def test_dev_lock_pins_runtime_and_dev_dependencies():
    pins = _pinned("dev.txt")
    wanted = _pyproject()["dependencies"] + _pyproject()["optional-dependencies"]["dev"]
    for requirement in wanted:
        assert _name(requirement) in pins, f"{requirement} is not locked in requirements/dev.txt"


def test_both_locks_agree_on_every_shared_version():
    base, dev = _pinned("base.txt"), _pinned("dev.txt")
    assert {name: dev[name] for name in base} == base


def test_locked_versions_satisfy_the_ranges_in_pyproject():
    """A pinned version must still be allowed by the range written in pyproject.toml."""
    from packaging.requirements import Requirement  # installed with pytest

    pins = _pinned("dev.txt")
    wanted = _pyproject()["dependencies"] + _pyproject()["optional-dependencies"]["dev"]
    for text in wanted:
        requirement = Requirement(text)
        version = pins[_name(text)]
        assert requirement.specifier.contains(version, prereleases=True), (
            f"{requirement.name}=={version} breaks the range {requirement.specifier}"
        )
