# Locked requirements

`pyproject.toml` lists what Miadi needs as loose ranges (`fastapi>=0.110`). The files here
pin the **exact versions** (and everything they pull in) so that your machine, CI and the
Docker image all install the same thing from the same commit.

| File | Used by | Contains |
|---|---|---|
| `base.txt` | Dockerfile (and so Render) | Runtime dependencies only |
| `dev.txt` | CI and local development | Runtime plus pytest, coverage, httpx and ruff |

Don't edit these files by hand. They are generated with [uv](https://docs.astral.sh/uv/)
(`pip install uv`) for Python 3.12 on any operating system (`--universal`).

## Install

```bash
pip install -r requirements/dev.txt     # development and tests
pip install -r requirements/base.txt    # what the Docker image installs
```

## Add or change a dependency

1. Edit the range in `pyproject.toml` (`dependencies`, or `dev` under `optional-dependencies`).
2. Regenerate both files, in this order, from the project folder:

```bash
uv pip compile pyproject.toml --universal --python-version 3.12 -o requirements/base.txt
uv pip compile pyproject.toml --extra dev --universal --python-version 3.12 -c requirements/base.txt -o requirements/dev.txt
```

3. Run `pytest`, then commit `pyproject.toml` and both files together.

## Upgrade everything

Add `--upgrade` to both commands above, run the tests, and commit the result.
Upgrade deliberately, in its own pull request, so a failing upgrade is easy to spot.
