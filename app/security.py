"""Password hashing and token creation.

Access tokens are short-lived signed JWTs sent in the `Authorization` header.
Refresh tokens are long random strings kept in an HttpOnly cookie; only their
SHA-256 hash is stored. See [Authentication](../auth.md) for the full flow.
"""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext

from app.config import settings

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")
"""Password hasher. Uses Argon2, and marks hashes from older schemes for upgrade."""


def hash_password(password: str) -> str:
    """Hash a password for storage.

    Args:
        password: The plain-text password.

    Returns:
        The Argon2 hash, including its salt and parameters.
    """
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Check a password against a stored hash.

    Args:
        password: The plain-text password to check.
        password_hash: The hash stored for the user.

    Returns:
        True if the password matches.
    """
    return pwd_context.verify(password, password_hash)


def create_access_token(user_id: uuid.UUID) -> tuple[str, int]:
    """Create a signed access token for a user.

    The token carries the user ID (`sub`), its issue and expiry times
    (`iat`, `exp`) and `type: "access"`, which `get_current_user` checks.

    Args:
        user_id: The user the token identifies.

    Returns:
        The encoded token and its lifetime in seconds.
    """
    expires_in = settings.access_token_expire_minutes * 60
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
        "type": "access",
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, expires_in


def decode_access_token(token: str) -> dict:
    """Verify an access token and return its claims.

    Args:
        token: The encoded token.

    Returns:
        The token's claims.

    Raises:
        jwt.PyJWTError: If the signature is invalid or the token has expired.
    """
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


def new_refresh_token() -> tuple[str, str]:
    """Generate a new refresh token.

    Returns:
        The raw token, which goes in the cookie, and its SHA-256 hash, which
        goes in the database.
    """
    raw = secrets.token_urlsafe(48)
    digest = hashlib.sha256(raw.encode()).hexdigest()
    return raw, digest


def hash_refresh_token(raw: str) -> str:
    """Hash a raw refresh token so it can be looked up in the database.

    Args:
        raw: The token from the cookie.

    Returns:
        Its SHA-256 hash as hex.
    """
    return hashlib.sha256(raw.encode()).hexdigest()


def refresh_token_expiry() -> datetime:
    """Return the expiry time for a refresh token issued now."""
    return datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
