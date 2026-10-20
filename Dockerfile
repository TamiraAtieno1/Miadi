FROM python:3.12-slim

WORKDIR /code

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY alembic.ini .
COPY alembic ./alembic
COPY entrypoint.sh .

# Run via `sh` so it works even if the executable bit is lost (e.g. on Windows).
CMD ["sh", "entrypoint.sh"]
