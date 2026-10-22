FROM python:3.12-slim

# Don't write .pyc files into the image, and show logs immediately.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Run as a dedicated user instead of root, so a bug or a hijacked process in the
# app can't change the container's system files or install anything.
RUN useradd --create-home --uid 10001 appuser

WORKDIR /code
# The app may write its local SQLite file here when no DATABASE_URL is set.
RUN chown appuser:appuser /code

# The locked file: the image gets the same versions that CI tested.
COPY requirements/base.txt requirements/base.txt
RUN pip install --no-cache-dir -r requirements/base.txt

COPY --chown=appuser:appuser app ./app
COPY --chown=appuser:appuser alembic.ini .
COPY --chown=appuser:appuser alembic ./alembic
COPY --chown=appuser:appuser entrypoint.sh .

USER appuser

# Run via `sh` so it works even if the executable bit is lost (e.g. on Windows).
CMD ["sh", "entrypoint.sh"]
