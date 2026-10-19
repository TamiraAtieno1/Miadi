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
| Slot already taken, already cancelled, rescheduling a cancelled appointment | 409 |
| Unknown doctor / appointment / patient | 404 |

**Database: PostgreSQL.**
Partial unique indexes, real transactions, and a realistic production path. SQLite would be simpler locally but cannot demonstrate the concurrency guarantee properly.

### 1.5 Assumptions (ambiguities I resolved)

_Edit these to match what you actually decide._

- Slots must start on :00 or :30; anything else is rejected.
- Appointments can't be booked in the past or (bonus) within 1 hour of now.
- Patients are identified by id with no authentication; auth is out of scope.
- A patient may hold multiple appointments, including at the same time with different doctors. _(Decide: should this be blocked?)_
- Cancelling an already-cancelled appointment returns 409.
- Rescheduling to the same slot returns 409 (no-op is treated as a conflict).
- Cancelling is allowed up to the appointment start. _(Decide: any cutoff?)_
- Doctors have no leave or holiday handling yet.

### 1.6 How it could grow

- Multiple clinics/locations: add a `Clinic` model and scope doctors and hours to it.
- Doctor leave and holidays: an `Exception` table overriding WorkingHours.
- Variable appointment lengths: add duration to appointment types.
- Auth and roles (patient / receptionist / doctor).
- Notifications (SMS/email reminders) via a background queue.
- Caching availability, and read replicas, if read traffic grows.

---

## 2. Running locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

# Optional: use Postgres (recommended). Without this it falls back to SQLite.
export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/clinic

uvicorn app.main:app --reload     # http://localhost:8000/docs
pytest -q                         # tests use in-memory SQLite unless DATABASE_URL is set
```

On startup the app creates the tables and seeds 5 doctors (Mon-Fri, 09:00-17:00 EAT) plus one demo patient if the database is empty.

## 3. CI/CD and Deployment

**Public URL:** https://miadi-xw8x.onrender.com

**Branch that deploys:** `main`. Work happens on feature branches; merging a PR into `main` triggers a deploy.

**Pipeline** (`.github/workflows/ci.yml`, GitHub Actions):
1. **On every pull request:** install dependencies and run `pytest` against a real Postgres 16 service container (so the partial unique index is tested on the same engine as production).
2. **On push to `main`** (a merged PR): run the same tests again, and only if they pass, call the Render deploy hook, which makes Render pull `main`, build the Docker image and restart the service.

Render's own auto-deploy is turned off so a deploy can never happen without passing tests. The hook URL is stored as the GitHub secret `RENDER_DEPLOY_HOOK_URL`.

## 4. AI Reflection

_Write this yourself from your own notes as you work, honesty is what's being graded. Keep a running log of prompts, what helped, and what was wrong._
