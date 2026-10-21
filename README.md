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
| **Doctor** | id, name, specialty | 5 seeded for now |
| **WorkingHours** | id, doctor_id, weekday (0-6), start_time, end_time | One row per doctor per working weekday. Separate from Doctor so hours can differ by day and a doctor can have days off. |
| **Patient** | id, name, phone, email | No auth in scope (see assumptions) |
| **Appointment** | id, doctor_id, patient_id, start_time (UTC), end_time (UTC), status (`booked` / `cancelled`), cancel_reason, cancelled_at, created_at, updated_at | Soft-cancelled, never deleted |

### 1.3 Components

```
Client -> Routers (HTTP, validation, status codes)
       -> Services (booking rules: working hours, past, 1h notice, conflicts)
       -> Models/DB (SQLAlchemy + PostgreSQL)
```

- **routers/**: thin HTTP layer (doctors, appointments, patients)
- **services/booking.py**: all booking logic, so it is testable without HTTP
- **schemas.py**: Pydantic request/response models
- **models.py**: ORM models
- **alembic/**: database migrations
- **tests/**: unit tests on services plus API tests

### 1.4 Key decisions and trade-offs

**Slots are computed, not stored.**
Availability = the doctor's working hours for that weekday, split into 30-minute slots, minus slots with a `booked` appointment.
- _Why:_ no slot rows to generate, expire or keep in sync; changing working hours takes effect immediately.
- _Trade-off:_ availability is computed per request. At this scale that is trivial. At large scale I would cache, or materialise slots in a table.

**Double-booking is prevented by the database, not only by code.**
A partial unique index on `(doctor_id, start_time) WHERE status = 'booked'`.
- _Why:_ checking "is it free?" and then inserting has a race window where two concurrent requests both pass the check. The index makes the second insert fail; I catch the integrity error and return 409.
- _Bonus:_ because the index only covers `booked` rows, a cancelled slot is bookable again with no extra logic.

**Soft cancel.**
Cancelling sets `status = cancelled` plus reason and timestamp. This keeps history and audit trail, and frees the slot via the partial index.

**Reschedule is one transaction.**
Validate the new slot as for a fresh booking, then update the appointment's times in a single transaction. If the new slot is taken or invalid, the original booking stays untouched. Rescheduling updates the existing row rather than creating a new one, so the appointment keeps its identity.

**Times stored in UTC; working hours in clinic local time.**
Working hours are defined in the clinic's timezone (Africa/Nairobi, EAT, UTC+3) and converted when computing slots. Clients send and receive ISO-8601 timestamps with an offset.

**Status codes.**

| Situation | Code |
|---|---|
| Created | 201 |
| Malformed input, misaligned slot, outside hours, in the past | 422 |
| Slot already taken, already cancelled, rescheduling a cancelled appointment, cancelling/rescheduling one that has already started, rescheduling to the time it already has | 409 |
| Unknown doctor / appointment / patient | 404 |

**Database: PostgreSQL.**
Partial unique indexes, real transactions, and a realistic production path. SQLite would be simpler locally but cannot demonstrate the concurrency guarantee properly.

### 1.5 Assumptions (ambiguities I resolved)

_Decisions I made where the brief was ambiguous._

- Slots start on :00 or :30; anything else is rejected (422).
- A slot is bookable only if it is not in the past and starts at least 1 hour from now (the bonus rule). Availability hides slots that are no longer bookable, so the list matches exactly what `POST /appointments` will accept.
- Clients must send timestamps with a UTC offset (e.g. `2026-10-26T09:00:00+03:00`). A timestamp without one is rejected (422) rather than guessed. Responses use clinic local time (+03:00).
- Patients are identified by id with no authentication; auth is out of scope. `POST /patients` and `GET /doctors` exist only so the API can be tried end to end.
- A patient may hold several appointments, including at the same time with different doctors (not blocked).
- Cancelling an already-cancelled appointment returns 409. A cancel reason is required and cannot be blank.
- Cancelling or rescheduling an appointment that has already started returns 409.
- Rescheduling keeps the same doctor; moving to the time it already has returns 409.
- "Upcoming appointments" means booked (not cancelled) appointments that haven't started yet.
- A doctor with no working-hours row for a weekday doesn't work that day, so availability there is an empty list (200), not an error.
- Doctors have no leave or holiday handling yet.

### 1.6 How it could grow

- Multiple clinics/locations: add a `Clinic` model and scope doctors and hours to it.
- Doctor leave and holidays: an `Exception` table overriding WorkingHours.
- Variable appointment lengths: add duration to appointment types.
- Auth and roles (patient / receptionist / doctor).
- Notifications (SMS/email reminders) via a background queue.
- Caching availability, and read replicas, if read traffic grows.

---

## 2. Setup and running

### Prerequisites
- Python 3.12+
- Optional: PostgreSQL 16 (or Docker). Without a `DATABASE_URL` the app falls back to a local SQLite file, which is fine for a quick look but is not what production runs.

### Option A: run with Python
```bash
git clone https://github.com/TamiraAtieno1/Miadi.git && cd Miadi
python -m venv .venv
source .venv/bin/activate          # Windows Git Bash: source .venv/Scripts/activate
pip install -r requirements-dev.txt

# Optional: use Postgres (recommended, matches production). See .env.example for the format.
export DATABASE_URL=postgresql://USER:PASSWORD@localhost:5432/clinic

alembic upgrade head               # create/update the tables
uvicorn app.main:app --reload      # http://localhost:8000/docs
```
On first start the app seeds 5 doctors (Mon-Fri, 09:00-17:00 EAT) and one demo patient if the database is empty.

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
alembic downgrade -1                                   # undo the last one
alembic revision --autogenerate -m "describe change"   # after editing app/models.py
```
Always read an autogenerated migration before committing it. A test (`tests/test_migrations.py`) fails if the migrations and the models ever drift apart.

The first deployment created its tables before Alembic was added, so the initial migration detects an existing schema and adopts it instead of failing.

### Running the tests and checks
```bash
pytest -q --cov                    # in-memory SQLite by default; fails below 99% coverage
ruff check . && ruff format --check .
```
The concurrency test only runs when `DATABASE_URL` points at Postgres:
```bash
DATABASE_URL=postgresql://USER:PASSWORD@localhost:5432/clinic_test pytest -q
```
Shared fixtures live in `tests/conftest.py`: each test gets a fresh set of tables.

### Configuration
| Variable | Purpose | Default |
|---|---|---|
| `DATABASE_URL` | Database connection string (`postgres://` and `postgresql://` are both accepted) | `sqlite:///./clinic.db` |
| `PORT` | Port the container listens on | `8000` |

### API summary

| Endpoint | What it does | Success | Errors |
|---|---|---|---|
| `GET /doctors/{id}/availability?date=YYYY-MM-DD` | Free 30-minute slots for the doctor on that clinic-local date | 200 | 404 unknown doctor, 422 bad date |
| `POST /appointments` | Book a slot (`doctor_id`, `patient_id`, `start_time`) | 201 | 404, 409 slot taken, 422 invalid slot |
| `PATCH /appointments/{id}/cancel` | Cancel with a `reason`; the slot becomes bookable again | 200 | 404, 409 already cancelled or started, 422 missing reason |
| `PATCH /appointments/{id}/reschedule` | Move to a new `start_time` (same doctor) | 200 | 404, 409 cancelled / slot taken / same time, 422 invalid slot |
| `GET /patients/{id}/appointments` _(bonus)_ | Upcoming booked appointments, soonest first | 200 | 404 |
| `GET /doctors`, `POST /patients` _(extras)_ | List doctors with their hours; create a patient | 200 / 201 | 422 |

Every expected failure has the same shape, e.g. `{"detail": "That slot is already booked.", "code": "slot_unavailable"}`.
Seeded data: doctors with ids 1-5 and one patient with id 1. Interactive docs are at `/docs`.

Try it (use a future weekday for the date):

```bash
BASE=https://miadi-xw8x.onrender.com
curl "$BASE/doctors/1/availability?date=2026-10-26"
curl -X POST "$BASE/appointments" -H "Content-Type: application/json" \
  -d '{"doctor_id": 1, "patient_id": 1, "start_time": "2026-10-26T09:00:00+03:00"}'
```

## 3. CI/CD and Deployment

**Public URL:** https://miadi-xw8x.onrender.com

### Branching
- `develop` is the default branch. Work is integrated and tested here.
- `prod` is the production branch. A push to `prod` deploys to Render.
- Each change gets its own short-lived branch (`feat/`, `fix/`, `docs/`, `chore/`, `ci/`, `test/`) and is merged into `develop` through a pull request with a description.
- To release, I open a pull request from `develop` into `prod` and merge it with a merge commit.

### Pipeline (GitHub Actions)
**`ci.yml`** runs on every pull request, on every push to `develop`, and when called by the deploy workflow:
1. `ruff check` and `ruff format --check`.
2. `pytest` against a real PostgreSQL 16 service container, so the partial unique index that prevents double booking is tested on the same engine as production.
3. Coverage must stay at or above 99% (`fail_under = 99`). The report is uploaded to Coveralls.

**`deploy.yml`** runs on push to `prod`:
1. Calls `ci.yml`, so the full test suite must pass first.
2. Only if the tests pass, calls the Render deploy hook, which makes Render pull `prod`, build the Docker image and restart the service.

Render's own auto-deploy is turned off, so a deploy can never skip the tests. The container's `entrypoint.sh` applies database migrations (`alembic upgrade head`) before the server starts.

### Secrets
No credentials are stored in the repository. The CI database password (`CI_DB_PASSWORD`) and the Render deploy hook URL (`RENDER_DEPLOY_HOOK_URL`) live in GitHub's Actions secrets, and the production `DATABASE_URL` is set as an environment variable in Render.

### Keeping the free tier awake
Render's free web service spins down after 15 minutes without traffic, so the first request after a quiet period is slow. UptimeRobot calls `/health` every 5 minutes to keep it warm and to alert on downtime.

### Free-tier limits
The free Render database expires 30 days after creation, so it would need to be recreated or upgraded for real use.

## 4. AI Reflection

_(Write this yourself from your own notes: what you asked an AI to help with, what helped, and what was wrong or needed fixing.)_