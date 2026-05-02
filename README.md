# Social Journal — Backend

Django REST Framework API for the Social Journal Personal Relationship Manager.

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

Copy the example env file and fill in your local values:
```bash
cp .env.example .env
```

Open `.env` and set the following:
```
SECRET_KEY=any-local-secret-key-string
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
DB_NAME=social_journal
DB_USER=postgres
DB_PASSWORD=your_postgres_password
DB_HOST=localhost
DB_PORT=5432
CORS_ALLOWED_ORIGINS=http://localhost:3000
```

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
| POST | `/api/auth/token/` | Login and obtain JWT tokens | None |
| POST | `/api/auth/token/refresh/` | Refresh access token | None |
| POST | `/api/auth/logout/` | Logout and blacklist refresh token | Required |
| GET | `/api/auth/mfa/setup/` | Generate MFA secret and QR URI | Required |
| POST | `/api/auth/mfa/verify/` | Verify TOTP code and enable MFA | Required |
| GET | `/api/users/me/` | Get current user profile | Required |
| PATCH | `/api/users/me/` | Update current user profile | Required |

For protected endpoints include the access token in the request header:
```
Authorization: Bearer <access_token>
```

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
