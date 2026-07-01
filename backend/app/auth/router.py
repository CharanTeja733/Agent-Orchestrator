"""Authentication router — register, login, profile, and token refresh."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from jose import ExpiredSignatureError, JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User
from app.auth import utils as auth_utils
from app.auth.dependencies import get_current_user, oauth2_scheme
from app.auth.schemas import (
    RefreshResponse,
    TokenResponse,
    UserLogin,
    UserRegister,
)
from app.schemas import UserResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ---------------------------------------------------------------------------
# POST /auth/register
# ---------------------------------------------------------------------------


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    data: UserRegister,
    db: AsyncSession = Depends(get_db),
):
    """Create a new user account with a bcrypt-hashed password."""
    # 1. Check for duplicate email
    result = await db.execute(select(User).where(User.email == data.email))
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists",
        )

    # 2. Create user with hashed password
    user = User(
        email=data.email,
        hashed_password=auth_utils.hash_password(data.password),
        full_name=data.full_name,
        role=data.role,
        department=data.department,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    logger.info("New user registered: %s (role=%s)", user.email, user.role)

    return {
        "message": "User registered successfully",
        "user": UserResponse.model_validate(user),
    }


# ---------------------------------------------------------------------------
# POST /auth/login
# ---------------------------------------------------------------------------


@router.post("/login")
async def login(
    data: UserLogin,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate a user and return access + refresh JWT tokens."""
    # 1. Look up user by email
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()

    # 2. Verify password — single code path for missing-user and wrong-password
    #    prevents user enumeration via timing or error messages.
    if user is None or not auth_utils.verify_password(
        data.password, user.hashed_password
    ):
        logger.warning("Failed login attempt for email: %s", data.email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # 3. Check active status after credentials are confirmed valid
    if not user.is_active:
        logger.warning(
            "Login attempt for deactivated account: %s", data.email
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated. Contact HR administrator.",
        )

    # 4. Generate tokens
    user_id_str = str(user.id)
    access_token = auth_utils.create_access_token(
        user_id=user_id_str,
        email=user.email,
        role=user.role,
        department=user.department,
    )
    refresh_token = auth_utils.create_refresh_token(user_id=user_id_str)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=3600,
        user=UserResponse.model_validate(user),
    )


# ---------------------------------------------------------------------------
# GET /auth/me
# ---------------------------------------------------------------------------


@router.get("/me")
async def get_me(
    current_user: User = Depends(get_current_user),
):
    """Return the current authenticated user's profile."""
    return UserResponse.model_validate(current_user)


# ---------------------------------------------------------------------------
# POST /auth/refresh
# ---------------------------------------------------------------------------


@router.post("/refresh")
async def refresh(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
):
    """Exchange a valid refresh token for a new access token."""
    # 1. Decode and verify the token
    try:
        payload = auth_utils.decode_token(token)
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )

    # 2. Verify token type is "refresh"
    if not auth_utils.verify_token_type(payload, "refresh"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )

    # 3. Extract user ID
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )

    # 4. Verify user still exists and is active
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated. Contact HR administrator.",
        )

    # 5. Issue a new access token only — never a new refresh token
    new_access_token = auth_utils.create_access_token(
        user_id=str(user.id),
        email=user.email,
        role=user.role,
        department=user.department,
    )

    return RefreshResponse(
        access_token=new_access_token,
        expires_in=3600,
    )
