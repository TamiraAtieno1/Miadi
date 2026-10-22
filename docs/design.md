# Design notes

Detailed reasoning behind Miadi's design. The overview (requirements, models and components) is in the [README](../README.md#1-system-design).

## Key decisions and trade-offs

**Slots are computed, not stored.**
Availability = the doctor's working hours for that weekday, split into 30-minute slots, minus slots held by a `booked` or `rescheduled` appointment.
- _Why:_ no slot rows to generate, expire or keep in sync; changing working hours takes effect immediately.
- _Trade-off:_ availability is computed per request. At this scale that is trivial. At large scale I would cache, or materialise slots in a table.

**Double-booking is prevented by the database, not only by code.**
A partial unique index on `(doctor_id, start_time) WHERE status IN ('booked', 'rescheduled')`.
- _Why:_ checking "is it free?" and then inserting has a race window where two concurrent requests both pass the check. The index makes the second insert fail; I catch the integrity error and return 409.
- _Bonus:_ because the index only covers active (`booked` or `rescheduled`) rows, a cancelled slot is bookable again with no extra logic.

**Soft cancel.**
Cancelling sets `status = cancelled` plus reason and timestamp. This keeps history and audit trail, and frees the slot via the partial index.

**Reschedule is one transaction.**
Validate the new slot as for a fresh booking, then update the appointment's times in a single transaction. If the new slot is taken or invalid, the original booking stays untouched. Rescheduling updates the existing row rather than creating a new one, so the appointment keeps its identity. After a successful reschedule the appointment's status becomes `rescheduled`; it still holds its slot, and the partial unique index covers `booked` and `rescheduled`.

**Times stored in UTC; working hours in clinic local time.**
Working hours are defined in the clinic's timezone (Africa/Nairobi, EAT, UTC+3) and converted when computing slots. Clients send and receive ISO-8601 timestamps with an offset.

**Status codes.**

| Situation | Code |
|---|---|
| Created | 201 |
| Malformed input, misaligned slot, outside hours, in the past | 422 |
| Slot already taken, already cancelled, rescheduling a cancelled appointment, cancelling/rescheduling one that has already started, rescheduling to the time it already has, someone else changed the same appointment at the same moment | 409 |
| Unknown doctor / appointment / patient | 404 |

**Database: PostgreSQL.**
Partial unique indexes, real transactions, and a realistic production path. SQLite would be simpler locally but cannot demonstrate the concurrency guarantee properly.

## Assumptions (ambiguities I resolved)

_Decisions I made where the brief was ambiguous._

- Slots start on :00 or :30; anything else is rejected (422).
- A slot is bookable only if it is not in the past and starts at least 1 hour from now (the bonus rule). Availability hides slots that are no longer bookable, so the list matches exactly what `POST /appointments` will accept.
- Clients must send timestamps with a UTC offset (e.g. `2026-10-26T09:00:00+03:00`). A timestamp without one is rejected (422) rather than guessed. Responses use clinic local time (+03:00).
- The JSON API has no authentication, as the brief describes: patients are identified by id. The browser pages do need a login (see [web-pages.md](web-pages.md)). `POST /patients` and `GET /doctors` exist only so the API can be tried end to end.
- A patient may hold several appointments, including at the same time with different doctors (not blocked).
- Cancelling an already-cancelled appointment returns 409. A cancel reason is required and cannot be blank.
- Cancelling or rescheduling an appointment that has already started returns 409.
- Rescheduling keeps the same doctor; moving to the time it already has returns 409.
- "Upcoming appointments" means booked or rescheduled (not cancelled) appointments that haven't started yet.
- A doctor with no working-hours row for a weekday doesn't work that day, so availability there is an empty list (200), not an error.
- Doctors have no leave or holiday handling yet.

## How it could grow

- Multiple clinics/locations: add a `Clinic` model and scope doctors and hours to it.
- Doctor leave and holidays: an `Exception` table overriding WorkingHours.
- Variable appointment lengths: add duration to appointment types.
- Protect the JSON API too (tokens or the same sessions), and add a receptionist role. Patient, doctor and admin logins already exist for the browser pages.
- Notifications (SMS/email reminders) via a background queue.
- Caching availability, and read replicas, if read traffic grows.
