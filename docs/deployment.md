# Deployment and operations

Summary in the [README](../README.md#3-cicd-and-deployment).

## Overview

**Public URL:** https://miadi-xw8x.onrender.com

## Branching
- `develop` is the default branch. Work is integrated and tested here.
- `prod` is the production branch. A push to `prod` deploys to Render.
- Each change gets its own short-lived branch (`feat/`, `fix/`, `docs/`, `chore/`, `ci/`, `test/`) and is merged into `develop` through a pull request with a description.
- To release, I open a pull request from `develop` into `prod` and merge it with a merge commit.

## Pipeline (GitHub Actions)
**`ci.yml`** runs on every pull request, on every push to `develop`, and when called by the deploy workflow:
1. `ruff check` and `ruff format --check`.
2. `pytest` against a real PostgreSQL 16 service container, so the partial unique index that prevents double booking is tested on the same engine as production.
3. Coverage must stay at or above 99% (`fail_under = 99`). The report is uploaded to Coveralls.

**`deploy.yml`** runs on push to `prod`:
1. Calls `ci.yml`, so the full test suite must pass first.
2. Only if the tests pass, calls the Render deploy hook, which makes Render pull `prod`, build the Docker image and restart the service.

Render's own auto-deploy is turned off, so a deploy can never skip the tests. The container's `entrypoint.sh` applies database migrations (`alembic upgrade head`) before the server starts.

## Secrets
No credentials are stored in the repository. The CI database password (`CI_DB_PASSWORD`) and the Render deploy hook URL (`RENDER_DEPLOY_HOOK_URL`) live in GitHub's Actions secrets, and the production `DATABASE_URL` is set as an environment variable in Render.

## Keeping the free tier awake
Render's free web service spins down after 15 minutes without traffic, so the first request after a quiet period is slow. UptimeRobot calls `/health` every 5 minutes to keep it warm and to alert on downtime.

## Free-tier limits
The free Render database expires 30 days after creation, so it would need to be recreated or upgraded for real use.
