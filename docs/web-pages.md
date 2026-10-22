# Web pages and logins

Besides the JSON API, Miadi serves a small set of HTML pages so people can use it in a browser.
They sit on top of the same booking services, so every rule (30-minute slots, one-hour notice,
no double booking, optimistic concurrency) applies exactly as it does for the API.

## Pages

| Who | Page | What it does |
|---|---|---|
| Everyone | `/login`, `/register` | Sign in. Patients can create their own account. |
| Patient | `/portal/patient` | Upcoming appointments, history, reschedule and cancel. |
| Patient | `/portal/patient/book` | Choose a doctor and a day, then book a free time. |
| Doctor | `/portal/doctor` | Own upcoming appointments by day; cancel with a reason. |
| Admin | `/portal/admin` | Every appointment with a status filter and headline counts; cancel any. |

`/` sends visitors to their own home page, or to the sign-in form.

## How it works

- **Accounts** live in a `users` table (migration `0004`): email, password hash, role
  (`patient`, `doctor` or `admin`) and a link to the doctor or patient record.
- **Passwords** are hashed with scrypt from the standard library and a random salt per user.
  The sign-in form gives the same answer for an unknown email and a wrong password, and does
  the same amount of work for both.
- **Sessions** are a signed cookie (`SameSite=Lax`, 8 hours). The cookie holds only the user id.
- **Roles** are checked on the server for every page. A patient or doctor who asks for
  someone else's appointment gets "we couldn't find that appointment", the same answer as for
  one that does not exist.
- **Errors** reuse the booking messages, shown as a one-time banner on the next page.

## Demo accounts

The seed command (`python -m app.seed`, which the container runs on start) creates a login
for the admin, each doctor and the demo patient, skipping any email that is already taken. The password comes from `DEMO_PASSWORD`
(default `miadi-demo`).

| Role | Email |
|---|---|
| Patient | `demo@example.com` |
| Doctor | `amina.wanjiru@example.com` (and the other doctors, `first.last@example.com`) |
| Admin | `admin@example.com` |

## Settings

| Variable | Purpose | Default |
|---|---|---|
| `SECRET_KEY` | Signs the session cookie. **Set it in production**, otherwise a random key is made at each start and everyone is signed out whenever the app restarts. | random |
| `SECURE_COOKIES` | Set to `1` when served over HTTPS so the cookie is never sent over plain HTTP. | off |
| `DEMO_PASSWORD` | Password for the demo accounts. | `miadi-demo` |
| `SHOW_DEMO_LOGINS` | Set to `0` to hide the demo accounts box on the sign-in page. | shown |

## Known limits

- The JSON API (`/appointments`, `/doctors`, `/patients`) is still open, as the brief describes.
  Only the HTML pages need a login.
- There is no rate limiting on sign-in and no password reset or email verification.
- Forms rely on `SameSite=Lax` cookies instead of CSRF tokens.
- Sign-in sessions cannot be revoked server-side before they expire.
