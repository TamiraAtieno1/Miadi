# Miadi: Clinic Booking API

[![CI](https://github.com/TamiraAtieno1/Miadi/actions/workflows/ci.yml/badge.svg?branch=develop)](https://github.com/TamiraAtieno1/Miadi/actions/workflows/ci.yml)
[![Coverage Status](https://coveralls.io/repos/github/TamiraAtieno1/Miadi/badge.svg?branch=develop)](https://coveralls.io/github/TamiraAtieno1/Miadi?branch=develop)

Miadi (Swahili for "appointment") is a REST API for booking, cancelling and rescheduling 30-minute appointments at a small clinic (5 doctors), built with FastAPI and PostgreSQL.

**Live URL:** https://miadi-xw8x.onrender.com
**API docs:** https://miadi-xw8x.onrender.com/docs

---

## 1. System Design

### 1.1 Requirements as I understood them

- Patients view free slots for a doctor on a given date, book one, cancel, and reschedule it.
- A patient's upcoming appointments can be listed (bonus).
- Each doctor has set working hours; appointments are fixed 30-minute slots.
- A booked slot must never be available to anyone else, even under simultaneous requests.
- The clinic is small today but should be able to grow.

### 1.2 Models

| Model | Key fields | Notes |
|---|---|---|
| **Doctor** | id, name, specialty, email (unique) | 5 seeded for now. The unique email is what stops duplicate doctor records. |
| **WorkingHours** | id, doctor_id, weekday (0-6), start_time, end_time | One row per doctor per working weekday. Separate from Doctor so hours can differ by day and a doctor can have days off. |
| **Patient** | id, name, phone, email (optional, unique, stored in lower case) | Can have a login (see [web pages](docs/web-pages.md)); the JSON API itself has no auth |
| **Appointment** | id, doctor_id, patient_id, start_time (UTC), end_time (UTC), status (`booked` / `rescheduled` / `cancelled`), cancel_reason, cancelled_at, created_at, updated_at | Soft-cancelled, never deleted |

### 1.3 Components

```
Client -> Routers (HTTP, validation, status codes)
       -> Services (booking rules: working hours, past, 1h notice, conflicts)
       -> Models/DB (SQLAlchemy + PostgreSQL)
```

- **routers/**: thin HTTP layer (doctors, appointments, patients)
- **services/**: all booking logic, split by job so it is testable without HTTP: `lookups.py` (database lookups), `slots.py` (slot validation rules), `booking.py` (book, cancel, reschedule) and `availability.py` (free slots and upcoming appointments)
- **schemas.py**: Pydantic request/response models
- **models.py**: ORM models
- **alembic/**: database migrations
- **tests/**: unit tests on services plus API tests

### 1.4 Key decisions at a glance

- **Slots are computed, not stored:** availability is the doctor's working hours split into 30-minute slots, minus booked ones.
- **Double-booking is stopped by the database:** a partial unique index on `(doctor_id, start_time) WHERE status IN ('booked', 'rescheduled')`, with a violation of that index (and only that one) turned into a 409.
- **Business rules are database constraints too**, so writes that bypass the API are refused as well: unique doctor and patient emails, allowed statuses, exactly-30-minute appointments, weekdays 0-6, working hours that end after they start, and a login that matches its role. See [design notes](docs/design.md#rules-enforced-by-the-database).
- **Soft cancel:** cancelling keeps the row (status, reason, timestamp) and frees the slot.
- **Reschedule is one transaction:** if the new slot is invalid or taken, the original booking is untouched.
**Concurrent changes to one appointment.**
Each appointment carries a `version` number. A cancel or reschedule only applies if the version is still the one it read, and bumps it. If two requests change the same appointment at once, the second is rejected with a 409 (`concurrent_change`) instead of silently overwriting the first. This is optimistic concurrency: no locks are held while the user decides; conflicts are detected when writing.

That protects overlapping requests. To protect a stale screen as well, every appointment in a response includes its `version`, and cancel and reschedule requests must send it back as `expected_version`. If the appointment changed after the caller loaded it (for example someone else rescheduled it), the request is refused with a 409 (`stale_version`) before anything is changed, and the caller reloads and decides again. The web pages do this with a hidden field in each form.
- **UTC in the database, clinic local time (Africa/Nairobi) for working hours.**
- **PostgreSQL** for production and CI; SQLite only as a local fallback.

The full reasoning and trade-offs, the status code table, every assumption I made where the brief was ambiguous, and how the design could grow are in [docs/design.md](docs/design.md).

---

## 2. Setup and running

### Prerequisites
- Python 3.12+
- Dependencies install from the locked files in `requirements/` (exact versions, the same ones CI and Docker use). See [requirements/README.md](requirements/README.md) to add or upgrade one.
- Optional: PostgreSQL 16 (or Docker). Without a `DATABASE_URL` the app falls back to a local SQLite file, which is fine for a quick look but is not what production runs.

### Option A: run with Python
```bash
git clone https://github.com/TamiraAtieno1/Miadi.git && cd Miadi
python -m venv .venv
source .venv/bin/activate          # Windows Git Bash: source .venv/Scripts/activate
pip install -r requirements/dev.txt

# Optional: use Postgres (recommended, matches production). See .env.example for the format.
export DATABASE_URL=postgresql://USER:PASSWORD@localhost:5432/clinic

alembic upgrade head               # create/update the tables
uvicorn app.main:app --reload      # http://localhost:8000/docs
```
`python -m app.seed` adds 5 doctors (Mon-Fri, 09:00-17:00 EAT) and one demo patient if the database has no doctors, and creates demo logins for the admin, each doctor and the patient (see [docs/web-pages.md](docs/web-pages.md)). It is safe to run again, and in Docker it runs automatically when the container starts.

### Option B: run with Docker
```bash
docker build -t miadi .
docker run --rm -p 8000:8000 -e DATABASE_URL=postgresql://user:pass@host:5432/clinic miadi
```
The container starts through `entrypoint.sh`, which applies migrations (`alembic upgrade head`) and then starts the API on `$PORT` (Render sets it; default 8000). Omit `DATABASE_URL` to use SQLite inside the container.

### Database migrations (Alembic)
The schema is managed with Alembic; migration files live in `alembic/versions/`. The database URL comes from `DATABASE_URL`.
```bash
alembic upgrade head                                   # apply all migrations
python -m app.seed                 # add the demo doctors and patient (safe to repeat)
alembic downgrade -1                                   # undo the last one
alembic revision --autogenerate -m "describe change"   # after editing app/models.py
```
Always read an autogenerated migration before committing it. A test (`tests/test_migrations.py`) fails if the migrations and the models ever drift apart.

The first deployment created its tables before Alembic was added, so the initial migration checks that the existing tables, columns, foreign keys and indexes match what it would have created, adopts them if they do, and stops with a list of the problems if they do not.

### Running the tests and checks
```bash
pytest -q --cov                    # in-memory SQLite by default; fails below 99% coverage
ruff check . && ruff format --check .
```
The concurrency test only runs when `DATABASE_URL` points at Postgres:
```bash
DATABASE_URL=postgresql://USER:PASSWORD@localhost:5432/clinic_test pytest -q
```
Shared fixtures live in `tests/conftest.py`: each test gets a fresh set of tables. Tests are organised by area: `tests/api` (HTTP), `tests/services` (booking rules), `tests/db` (database, concurrency, migrations) and `tests/project`.

### Configuration
| Variable | Purpose | Default |
|---|---|---|
| `DATABASE_URL` | Database connection string (`postgres://` and `postgresql://` are both accepted) | `sqlite:///./clinic.db` |
| `PORT` | Port the container listens on | `8000` |
| `SECRET_KEY` | Signs the sign-in cookie of the web pages. Set it in production, or everyone is signed out whenever the app restarts | random per start |
| `SECURE_COOKIES` | `1` on HTTPS so the cookie is never sent over plain HTTP | off |
| `DEMO_PASSWORD` | Password of the demo accounts created by `python -m app.seed` | `miadi-demo` |
| `SHOW_DEMO_LOGINS` | `0` hides the demo accounts box on the sign-in page | shown |

The browser pages, roles and demo accounts are described in [docs/web-pages.md](docs/web-pages.md).

### API summary

| Endpoint | What it does | Success | Errors |
|---|---|---|---|
| `GET /doctors/{id}/availability?date=YYYY-MM-DD` | Free 30-minute slots for the doctor on that clinic-local date | 200 | 404 unknown doctor, 422 bad date |
| `POST /appointments` | Book a slot (`doctor_id`, `patient_id`, `start_time`) | 201 | 404, 409 slot taken, 422 invalid slot |
| `PATCH /appointments/{id}/cancel` | Cancel with a `reason` and the `expected_version` you last saw; the slot becomes bookable again | 200 | 404, 409 stale version / already cancelled / started / changed at the same moment, 422 missing reason or version |
| `PATCH /appointments/{id}/reschedule` | Move to a new `start_time` (same doctor), sending the `expected_version` you last saw | 200 | 404, 409 stale version / cancelled / slot taken / same time / changed at the same moment, 422 invalid slot or missing version |
| `GET /patients/{id}/appointments` _(bonus)_ | Upcoming (booked or rescheduled) appointments, soonest first | 200 | 404 |
| `GET /doctors`, `POST /patients` _(extras)_ | List doctors with their hours; create a patient | 200 / 201 | 409 email already used, 422 |

Every expected failure has the same shape, e.g. `{"detail": "Sorry, that slot is already booked. Please choose another time.", "code": "slot_unavailable"}`. Invalid input returns 422 with code `validation_error` and one plain sentence in `detail`.
Seeded data: doctors with ids 1-5 and one patient with id 1. Interactive docs are at `/docs`.

Try it (use a future weekday for the date):

```bash
BASE=https://miadi-xw8x.onrender.com
curl "$BASE/doctors/1/availability?date=2026-10-26"
curl -X POST "$BASE/appointments" -H "Content-Type: application/json" \
  -d '{"doctor_id": 1, "patient_id": 1, "start_time": "2026-10-26T09:00:00+03:00"}'
```

---

## 3. CI/CD and Deployment

**Public URL:** https://miadi-xw8x.onrender.com

- **Branches:** `develop` is the default branch where work is integrated and tested; `prod` is production, and a push to it deploys to Render. Every change is a short-lived branch (`feat/`, `fix/`, `docs/`, `chore/`, `ci/`, `test/`) merged into `develop` by pull request. A release is a pull request from `develop` into `prod`.
- **`ci.yml`** (every pull request and push to `develop`): ruff lint and format check, then the tests against a real PostgreSQL 16 service, with coverage held at 99% or more and reported to Coveralls.
- **`deploy.yml`** (push to `prod`): runs `ci.yml` first, and only if it passes calls the Render deploy hook. The container applies database migrations before the server starts.
- **No secrets in the repository:** they live in GitHub Actions secrets and Render environment variables.

Details (secrets, keep-alive monitoring, free-tier limits) are in [docs/deployment.md](docs/deployment.md).

## 4. AI Reflection

### 1. What did I use AI for across the four sections?

- **1. System design:** talking through the design options (a database constraint against double-booking, optimistic versioning, an append-only history table instead of full event sourcing) and drafting the design notes. I made the final choices.
- **2. Setup and running:** scaffolding the FastAPI services, Alembic migrations, the pytest suite, the web pages and logins, and the Docker setup. I ran everything myself on my own machine.
- **3. CI/CD and deployment:** drafting the GitHub Actions workflow, locked requirements, the non-root Docker image and the Render deploy steps. I did the setup and every push, merge and release myself.
- **4. This reflection and the docs:** structuring the README and PR descriptions. 

### 2. One example where an AI suggestion improved my work

The code review pointed out that the `version` column only protected overlapping database writes, not a stale screen: someone could open an appointment, have it rescheduled by someone else, then cancel it from the old page. I prompted: for example: how do I stop a user acting on an out-of-date appointment?. The suggestion was to require `expected_version` on cancel and reschedule and check it before any state change, refusing with `409 stale_version`, with the web forms carrying the version in a hidden field. I accepted it because it closed a real gap without adding locks.

### 3. One example where AI output was wrong or incomplete, and how I caught it

The first test-database safety guard treated a SQLite file as safe if "test" appeared anywhere in its path, so a temporary folder with "test" in its name could pass the check. for example: the tests for the guard failed, I noticed it in review. It was changed to check only the file name.

### 4. Two decisions I made without AI, and why I trusted my judgment

1. **Doing every Git and GitHub step myself.** I created each branch, opened and merged each PR and ran each release to `prod`. I trusted my own judgment here because releases affect the live site and I wanted to know exactly what went out.
2. **Deciding which review points to take and which to skip.**  for example: I skipped the cleanup refactors because of time constraints. I trusted my own judgment because I knew how much time I had and which changes carried the most risk.
