# Collective Behavior Analytics

A web-based system for the management and tranformation of experiment data for collective behavior analysis, storing every result with its version history so analyses can be traced and reproduced.

The system is a single FastAPI backend, a PostgreSQL database and a React frontend.

## Interface

The frontend has five views:

1. **Authentication.** Login and registration.
2. **Organization.** The list of laboratories.
3. **Laboratory.** The experiments of one laboratory.
4. **Experiment.** Videos, data import, batch analysis and experiment-level collective-behavior results.
5. **Video.** The video analysis pipeline.

## Requirements

- Python 3.11
- Node.js 18 or later (22 was used in development)
- PostgreSQL 14 or later

## Setup

### 1. Clone repository

```bash
git clone https://github.com/EinerBarba/CollectiveBehaviorAnalyticsSuite.git
cd CollectiveBehaviorAnalyticsSuite

```

### 2. Create the database

Open a PostgreSQL shell (`psql -U postgres`) and run the following. Use a custom password for the database user.

```sql
CREATE ROLE collective_user WITH LOGIN PASSWORD 'password';
CREATE DATABASE collective_db OWNER collective_user;
\c collective_db
GRANT ALL PRIVILEGES ON SCHEMA public TO collective_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO collective_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO collective_user;
\q
```

Then create the tables:

```bash
psql -U collective_user -d collective_db -h localhost -f schema.sql
```

### 3. Configure the environment

Create a file named `.env` in the project root. The backend and the frontend both read it. Replace the Database URL password with the one chosen, and the JWT Secret with a custom one.

```ini
DATABASE_URL=postgresql+asyncpg://collective_user:password@localhost:5432/collective_db
JWT_SECRET=replace-with-a-long-random-string
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7
STORAGE_ROOT=./storage
COOKIE_SECURE=false
COOKIE_DOMAIN=localhost
CORS_ORIGINS=http://localhost:5173

# Optional: only if the backend is not at http://localhost:8000
# VITE_API_URL=http://localhost:8000
```

| Setting | Meaning |
|---|---|
| `DATABASE_URL` | Connection string. It must use the `postgresql+asyncpg` driver. |
| `JWT_SECRET` | Secret used to sign access tokens. Use a long random value and keep it private. |
| `JWT_ALGORITHM` | Signing algorithm for access tokens. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Lifetime of an access token. |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Lifetime of a refresh token. |
| `STORAGE_ROOT` | Folder where uploaded videos and all results are written. It is created as needed. |
| `COOKIE_SECURE` | Set to `true` when serving over HTTPS. Use `false` for local development. |
| `COOKIE_DOMAIN` | Domain for the refresh-token cookie. Use `localhost` for local development. |
| `CORS_ORIGINS` | Comma-separated list of frontend addresses allowed to call the API. |
| `VITE_API_URL` | Optional. Backend address used by the frontend. Defaults to `http://localhost:8000`. |

### 4. Install and run the backend

Create a virtual environment from the project root, install the dependencies and start the server.

```powershell
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

The interactive API documentation is then available at http://localhost:8000/docs.

### 5. Install and run the frontend

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The development server uses this fixed port, so it must be free and must match `CORS_ORIGINS`.

### 6. Create your first account

On the login screen, register a new account. No account exists after the schema is created.

Some actions, such as permanently deleting a video, require a system administrator. To promote an account, run this in `psql`, using your own email address:

```sql
UPDATE users SET is_system_admin = true WHERE email = 'you@example.com';
```

## Repository layout

```
app/
  main.py            application entry point
  config.py          settings read from .env
  routers/           API endpoints
  jobs/              background jobs (detection, tracking, kinematics, analysis, imports)
  cv/                plate detection, subject detection, light tracking
  tracking/          tracker, kinematics, CSV input and output
  analysis/          order parameters, clustering, Markov model
  models/, schemas/  database models and API schemas
frontend/            React application
schema.sql           database schema
```

## Building the documentation

```bash
pip install -r docs/requirements.txt
mkdocs build --strict # writes the static site to folder site/
```
