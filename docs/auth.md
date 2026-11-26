# Authentication

Users log in with an email and password. The backend then uses two kinds of token: a short-lived **access token** for API calls, and a long-lived **refresh token** for getting new access tokens without logging in again.

## Passwords

Passwords are hashed with **Argon2** before storage, and only the hash is kept. Hashes include their own salt and settings.

## Access tokens

- A signed JWT, sent with every request in the `Authorization: Bearer <token>` header.
- It carries the user's ID (`sub`), its issue and expiry times, and `type: "access"`.
- It lasts `ACCESS_TOKEN_EXPIRE_MINUTES`, and is signed with `JWT_SECRET` using `JWT_ALGORITHM`.
- The frontend keeps it in memory and in session storage, never in a cookie.

Endpoints that need a user check the token with `get_current_user`. A request is rejected with 401 if the token is missing, invalid, expired or of the wrong type, or if the user no longer exists or has been deactivated.

## Refresh tokens

- A random 64-character string, sent to the browser in an **HttpOnly cookie** named `refresh_token`. Scripts on the page cannot read it.
- The cookie is restricted to the path `/auth` and to same-site requests, and is marked secure when `COOKIE_SECURE` is true. It lasts `REFRESH_TOKEN_EXPIRE_DAYS`.
- Only its **SHA-256 hash** is stored in the database, together with the browser's user agent and IP address.

### Rotation

Each call to `POST /auth/refresh` revokes the refresh token it was given and issues a new one, so every refresh token is used once. Tokens from the same login share a **family ID**, and each revoked token points at the one that replaced it.

### Reuse detection

If a refresh token that was already revoked is presented again:

- **Within 60 seconds** of its revocation, it is treated as an honest race. Two browser tabs, or a quick reload, can both refresh with the same cookie before the browser stores the new one. The backend finds the family's newest live token and rotates that instead.
- **After 60 seconds**, it is treated as a stolen token. Every live token in the family is revoked, the cookie is cleared, and the user must log in again.

### Logout

`POST /auth/logout` revokes the current refresh token and clears the cookie. The access token stays valid until it expires, since access tokens are not tracked.

## How the frontend uses them

- After login, it schedules a refresh at 80% of the access token's lifetime, but never sooner than 10 seconds.
- If a request gets a 401, it refreshes once and retries the request.
- Concurrent refreshes share one request.
- If refreshing fails, the session has expired and the user is returned to the login screen.

## Rate limits

Per client IP address:

| Endpoint | Limit |
|---|---|
| `POST /auth/register` | 5 per minute |
| `POST /auth/login` | 10 per minute |
| `POST /auth/refresh` | 30 per minute |

## Permissions

- **Logged-in users** can use every endpoint that requires authentication.
- **System administrators** (`is_system_admin`) can also delete videos permanently. There is no endpoint to grant this; it is set directly in the database. The system is designed to have few system administrators, who would already need direct access to the database in the first place.
- **Roles** can be assigned per laboratory or experiment, but are only used to filter which runs a user sees.

## Code

`app.security` and `app.deps`. See the [core reference](reference/core.md). The endpoints are in `app/routers/auth.py` and documented at `/docs`.
