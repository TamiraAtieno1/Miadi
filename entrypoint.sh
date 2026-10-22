#!/bin/sh
# Container start-up: apply database migrations, add the demo data if the database is
# empty, then run the API on the port the platform provides. Render injects PORT;
# default to 8000 for local runs.
set -e
alembic upgrade head
python -m app.seed
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
