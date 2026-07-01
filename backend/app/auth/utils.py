"""Token and password utility functions for the auth module."""

import uuid
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings

# ---------------------------------------------------------------------------
# Password hashing (passlib + bcrypt)
# ---------------------------------------------------------------------------

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt. Auto-generates salt."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a bcrypt hash.

    Uses constant-time comparison (built into passlib).
    """
    return pwd_context.verify(plain_password, hashed_password)


# ---------------------------------------------------------------------------
# JWT token creation and verification
# ---------------------------------------------------------------------------

ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 7
ALGORITHM = "HS256"


def create_access_token(
    user_id: str, email: str, role: str, department: str
) -> str:
    """Create a JWT access token with user claims and 1-hour expiry."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "department": department,
        "type": "access",
        "exp": now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        "iat": now,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    """Create a JWT refresh token with 7-day expiry.

    Contains minimal claims — only ``sub`` and ``type``.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "type": "refresh",
        "exp": now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        "iat": now,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and verify a JWT token.

    Returns the token payload as a dict.
    Raises ``jose.JWTError`` (or ``ExpiredSignatureError`` subclass) on failure.
    """
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])


def verify_token_type(payload: dict, expected_type: str) -> bool:
    """Check that the ``type`` claim matches the expected value.

    Used to prevent refresh tokens from being used as access tokens and
    vice versa.
    """
    return payload.get("type") == expected_type
