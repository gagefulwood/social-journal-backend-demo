# Social Journal - Backend

Django REST Framework API for the private Social Journal relationship journal.

---

## Prerequisites

Make sure you have the following installed on your machine before starting:

- Python 3.12+
- PostgreSQL
- Git

---

## Setup

### 1. Clone the repository
```bash
git clone https://github.com/gagefulwood/social-journal-backend.git
cd social-journal-backend
```

### 2. Create and activate a virtual environment
```bash
python -m venv .venv
```
```bash
# Mac/Linux
source .venv/bin/activate

# Windows
.venv\Scripts\activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Create your environment file

The repository does not currently include an `.env.example`. Create a local
`.env` file (it is ignored by Git) with the database and application values:
```
SECRET_KEY=any-local-secret-key-string
DB_NAME=social_journal
DB_USER=postgres
DB_PASSWORD=your_postgres_password
DB_HOST=localhost
DB_PORT=5432
CORS_ALLOWED_ORIGINS=http://localhost:3000
```

For local development, you can temporarily bypass the MFA verification step
without removing a user's MFA setup:
```
DISABLE_MFA_REQUIREMENT=True
```

This only changes whether login/refresh responses report `mfa_pending`; the MFA
setup and verification endpoints remain available.

### 5. Create the PostgreSQL database

Make sure PostgreSQL is running, then:
```bash
psql -U postgres
CREATE DATABASE social_journal;
\q
```

### 6. Run migrations
```bash
python manage.py migrate
```

### 7. Create a superuser (for Django admin access)
```bash
python manage.py createsuperuser
```

### 8. Start the development server
```bash
python manage.py runserver
```

The API will be available at `http://127.0.0.1:8000/`.
Django admin will be available at `http://127.0.0.1:8000/admin/`.

---

## Key Endpoints

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| POST | `/api/auth/register/` | Register a new account | None |
| POST | `/api/auth/token/` | Login and set JWT cookies | None |
| POST | `/api/auth/token/refresh/` | Refresh JWT cookies | None |
| POST | `/api/auth/logout/` | Logout and blacklist refresh token | Required |
| GET | `/api/auth/mfa/setup/` | Generate MFA secret and QR URI | Required |
| POST | `/api/auth/mfa/verify/` | Verify TOTP code and enable MFA | Required |
| GET | `/api/auth/me/` | Get current user profile | Required |
| PATCH | `/api/auth/me/` | Update current user profile | Required |

Protected endpoints authenticate through httpOnly JWT cookies. API clients must send
credentials with requests; access and refresh token strings are not returned in JSON
response bodies.

---

## Project Structure
```
social-journal-backend/
├── config/          # Django project settings and root URLs
├── users/           # Auth, JWT, MFA, user profile
├── contacts/        # Contact management
├── events/          # Event logging
├── journals/        # Logs, reflections, and exercises
├── media/           # Uploads and contact profile pictures
├── dashboard/       # Aggregated dashboard data
├── lookups/         # Lookup tables (moods, categories, etc.)
├── core/            # Shared permissions, throttles, pagination
└── requirements.txt
```

---

## Running Checks

To verify the project is configured correctly:
```bash
python manage.py check
```

Should return: `System check identified no issues.`

## Populate an Existing Account

Add an idempotent demo dataset to one existing account by exact username,
email address, or full name:

```bash
python manage.py populate_account "gage"
```

Preview the records without saving anything:

```bash
python manage.py populate_account "gage@example.com" --dry-run
```

The command adds demo Contacts, categorized Facts, typed and statused Observations,
Events, participants, Logs, Reflections, and Exercises. Its Event history includes
ten shared moments in each of four rolling 30-day periods, distributed evenly
across the five demo Contacts. Fact categories are scoped to the selected account;
standard Observation markers are reused when available. Alex's demo context includes
three pinned Facts, three pinned Observations, and unpinned records with deterministic
pin ordering so both Context management and Overview carousel states are visible. The
command never creates a user or deletes existing data. Ambiguous full names are
rejected; use the account's username or email instead.

## Contact Context Pinning

Facts and Observations return these read-only fields:

```json
{
  "is_pinned": true,
  "pinned_at": "2026-07-11T18:30:00Z"
}
```

Use the explicit nested actions to change pin state; an empty request body is
expected and repeated calls are safe:

| Method | Endpoint |
|--------|----------|
| POST | `/api/contacts/{contact_id}/facts/{fact_id}/pin/` |
| POST | `/api/contacts/{contact_id}/facts/{fact_id}/unpin/` |
| POST | `/api/contacts/{contact_id}/observations/{observation_id}/pin/` |
| POST | `/api/contacts/{contact_id}/observations/{observation_id}/unpin/` |

Both nested list endpoints accept `pinned=true` or `pinned=false` and explicit
`ordering=pinned_at` or `ordering=-pinned_at`. For example:

```text
GET /api/contacts/{contact_id}/observations/?pinned=true&ordering=-pinned_at
```

Explicit pin ordering places unpinned records last. Omitting `ordering` preserves
the resource's normal list order. Observation lists continue to exclude archived
records unless `status=archived` or the compatibility `is_active` filter requests
them. All routes are authenticated and scoped through the active Contact owner;
another user's identifier is returned as not found.
