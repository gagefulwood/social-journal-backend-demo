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

Add a small, idempotent demo dataset to one existing account by exact username,
email address, or full name:

```bash
python manage.py populate_account "gage"
```

Preview the records without saving anything:

```bash
python manage.py populate_account "gage@example.com" --dry-run
```

The command adds demo Contacts, Facts, Observations, Events, participants, Logs,
Reflections, and Exercises. It never creates a user or deletes existing data. An
ambiguous full name is rejected; use the account's username or email instead.
