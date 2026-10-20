# Miadi: Clinic Booking API

Miadi (Swahili for "appointment") is a REST API for booking, cancelling and rescheduling 30-minute appointments at a small clinic (5 doctors), built with FastAPI and PostgreSQL.

**Live URL:** https://miadi-xw8x.onrender.com
**API docs:** https://miadi-xw8x.onrender.com/docs

---

## 1. System Design

### 1.1 Requirements as I understood them

- Patients view free slots for a doctor on a given date, book one, and cancel.
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

- **routers/**: thin HTTP layer
- **services/**: all booking logic, so it is testable without HTTP
- **schemas/**: Pydantic request/response models
- **models/**: ORM models
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
export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/clinic

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
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/clinic_test pytest -q
```
Shared fixtures live in `tests/conftest.py`: each test gets a fresh set of tables.

### Configuration
| Variable | Purpose | Default |
|---|---|---|
| `DATABASE_URL` | Database connection string (`postgres://` and `postgresql://` are both accepted) | `sqlite:///./clinic.db` |
| `PORT` | Port the container listens on | `8000` |
