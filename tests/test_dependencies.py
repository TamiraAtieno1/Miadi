"""pyproject.toml is the source of truth for dependencies; the requirements files mirror it."""

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _requirements(name: str) -> set[str]:
    lines = (ROOT / name).read_text().splitlines()
    return {
        line.strip() for line in lines if line.strip() and not line.lstrip().startswith(("#", "-r"))
    }


def _pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]


def test_requirements_txt_matches_pyproject_dependencies():
    assert _requirements("requirements.txt") == set(_pyproject()["dependencies"])


def test_requirements_dev_txt_matches_pyproject_dev_extra():
    assert _requirements("requirements-dev.txt") == set(
        _pyproject()["optional-dependencies"]["dev"]
    )
