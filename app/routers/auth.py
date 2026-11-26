import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.models import RefreshToken, User
from app.schemas.auth import AccessTokenResponse, LoginRequest, RegisterRequest, UserOut
from app.security import (
    create_access_token,
    hash_password,
    hash_refresh_token,
    new_refresh_token,
    refresh_token_expiry,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])
limiter = Limiter(key_func=get_remote_address)

REFRESH_COOKIE_NAME = "refresh_token"


def _set_refresh_cookie(response: Response, raw_token: str):
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=raw_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        domain=settings.cookie_domain,
        max_age=settings.refresh_token_expire_days * 24 * 3600,
        path="/auth",
    )


async def _issue_tokens(db: AsyncSession, user: User, response: Response, request: Request, family_id: uuid.UUID | None = None):
    access_token, expires_in = create_access_token(user.id)
    raw_refresh, refresh_hash = new_refresh_token()
    row = RefreshToken(
        user_id=user.id,
        token_hash=refresh_hash,
        family_id=family_id or uuid.uuid4(),
        expires_at=refresh_token_expiry(),
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
    )
    db.add(row)
    await db.commit()
    _set_refresh_cookie(response, raw_refresh)
    return AccessTokenResponse(access_token=access_token, expires_in=expires_in, user=UserOut.model_validate(user))


@router.post("/register", response_model=AccessTokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def register(request: Request, body: RegisterRequest, response: Response, db: AsyncSession = Depends(get_db)):
    existing = (await db.execute(select(User).where(User.email == body.email))).scalar_one_or_none()
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    user = User(email=body.email, full_name=body.full_name, password_hash=hash_password(body.password))
    db.add(user)
    await db.flush()
    return await _issue_tokens(db, user, response, request)


@router.post("/login", response_model=AccessTokenResponse)
@limiter.limit("10/minute")
async def login(request: Request, body: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    user = (await db.execute(select(User).where(User.email == body.email))).scalar_one_or_none()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account disabled")
    return await _issue_tokens(db, user, response, request)


@router.post("/refresh", response_model=AccessTokenResponse)
@limiter.limit("30/minute")
async def refresh(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    raw_token = request.cookies.get(REFRESH_COOKIE_NAME)
    if not raw_token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing refresh token")

    token_hash = hash_refresh_token(raw_token)
    row = (await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))).scalar_one_or_none()

    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")

    now = datetime.now(timezone.utc)
    if row.expires_at < now:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token expired")

    if row.revoked_at is not None:
        # Grace window: multiple tabs or a quick page reload can race to refresh
        # with the same cookie before the browser stores the rotated one.
        # Only treat as suspected theft if the token was revoked more than 60 s ago.
        from datetime import timedelta
        if now - row.revoked_at > timedelta(seconds=60):
            await db.execute(
                update(RefreshToken)
                .where(RefreshToken.family_id == row.family_id, RefreshToken.revoked_at.is_(None))
                .values(revoked_at=now)
            )
            await db.commit()
            response.delete_cookie(REFRESH_COOKIE_NAME, path="/auth")
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token reuse detected")
        # Within grace window: find the replacement token the browser hasn't received yet
        current = (await db.execute(
            select(RefreshToken)
            .where(RefreshToken.family_id == row.family_id, RefreshToken.revoked_at.is_(None))
            .order_by(RefreshToken.created_at.desc())
        )).scalars().first()
        if current is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token no longer valid")
        # Revoke the current live token and re-issue, just like a normal rotation
        row = current

    user = (await db.execute(select(User).where(User.id == row.user_id))).scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User inactive or not found")

    row.revoked_at = datetime.now(timezone.utc)
    await db.flush()

    tokens = await _issue_tokens(db, user, response, request, family_id=row.family_id)

    new_row = (await db.execute(
        select(RefreshToken).where(RefreshToken.family_id == row.family_id, RefreshToken.id != row.id, RefreshToken.revoked_at.is_(None))
    )).scalars().first()
    if new_row:
        row.replaced_by = new_row.id
        await db.commit()

    return tokens


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    raw_token = request.cookies.get(REFRESH_COOKIE_NAME)
    if raw_token:
        token_hash = hash_refresh_token(raw_token)
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.token_hash == token_hash, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(timezone.utc))
        )
        await db.commit()
    response.delete_cookie(REFRESH_COOKIE_NAME, path="/auth")


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return UserOut.model_validate(user)
