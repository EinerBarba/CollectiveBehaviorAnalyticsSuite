"""FastAPI dependencies that identify the current user.

Endpoints declare `Depends(get_current_user)` to require a logged-in user, or
`Depends(get_current_admin)` to require a system administrator. Roles stored
in `role_assignments` are not checked here.
"""

import uuid
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User
from app.security import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)
"""Reads the `Authorization: Bearer <token>` header. Missing headers are handled
by `get_current_user` rather than rejected here."""


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Return the user identified by the request's access token.

    Args:
        creds: The bearer credentials, if any.
        db: Database session.

    Returns:
        The active user the token belongs to.

    Raises:
        HTTPException: 401 if there is no token, the token is invalid, expired
            or not an access token, or the user is missing or deactivated.
    """
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        payload = decode_access_token(creds.credentials)
        if payload.get("type") != "access":
            raise ValueError("wrong token type")
        user_id = uuid.UUID(payload["sub"])
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")

    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User inactive or not found")
    return user


async def get_current_admin(user: User = Depends(get_current_user)) -> User:
    """Return the current user, requiring system administrator rights.

    Args:
        user: The logged-in user.

    Returns:
        The same user.

    Raises:
        HTTPException: 403 if the user is not a system administrator.
    """
    if not user.is_system_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administrator access required")
    return user
