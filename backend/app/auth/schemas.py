"""Pydantic schemas specific to authentication (register, login, tokens)."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, field_validator

from app.schemas import UserResponse, UserRole


class UserRegister(BaseModel):
    """Schema for the POST /auth/register endpoint."""

    email: EmailStr
    password: str
    full_name: str
    role: UserRole
    department: str

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Enforce password complexity: ≥8 chars, uppercase, lowercase, digit."""
        if len(v) < 8:
            raise ValueError(
                "Password must be at least 8 characters with "
                "uppercase, lowercase, and digit"
            )
        if not any(c.isupper() for c in v):
            raise ValueError(
                "Password must be at least 8 characters with "
                "uppercase, lowercase, and digit"
            )
        if not any(c.islower() for c in v):
            raise ValueError(
                "Password must be at least 8 characters with "
                "uppercase, lowercase, and digit"
            )
        if not any(c.isdigit() for c in v):
            raise ValueError(
                "Password must be at least 8 characters with "
                "uppercase, lowercase, and digit"
            )
        return v

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, v: str) -> str:
        """Enforce full_name: 2-255 characters."""
        if len(v.strip()) < 2:
            raise ValueError("Full name must be at least 2 characters")
        if len(v) > 255:
            raise ValueError("Full name must be at most 255 characters")
        return v.strip()

    @field_validator("department")
    @classmethod
    def validate_department(cls, v: str) -> str:
        """Enforce department: non-empty, max 100 characters."""
        if not v.strip():
            raise ValueError("Department must not be empty")
        if len(v) > 100:
            raise ValueError("Department must be at most 100 characters")
        return v.strip()


class UserLogin(BaseModel):
    """Schema for the POST /auth/login endpoint."""

    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """Schema returned by POST /auth/login."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse


class RefreshResponse(BaseModel):
    """Schema returned by POST /auth/refresh."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int
