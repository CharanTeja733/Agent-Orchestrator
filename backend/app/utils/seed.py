"""Database seeding — inserts demo users on first run, skips if data exists."""

from __future__ import annotations

import bcrypt
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_connection


def _hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

DEMO_USERS = [
    {
        "email": "admin@company.com",
        "password": "admin123",
        "full_name": "Admin User",
        "role": "hr_admin",
        "department": "hr",
    },
    {
        "email": "john@company.com",
        "password": "john123",
        "full_name": "John Doe",
        "role": "employee",
        "department": "engineering",
    },
    {
        "email": "sarah@company.com",
        "password": "sarah123",
        "full_name": "Sarah Smith",
        "role": "manager",
        "department": "sales",
    },
    {
        "email": "priya@company.com",
        "password": "priya123",
        "full_name": "Priya Sharma",
        "role": "employee",
        "department": "hr",
    },
]


async def seed_users() -> None:
    """Insert demo users if the ``users`` table is empty.

    Idempotent — checks for existing rows before inserting anything.
    Uses parameterized queries (``$1``, ``$2``, …) — no string formatting.
    """
    conn = await get_db_connection()
    try:
        # Check whether users already exist
        count = await conn.fetchval("SELECT COUNT(*) FROM users")
        if count > 0:
            print(f"{count} users already exist, skipping seed")
            return

        # Insert demo users with bcrypt-hashed passwords
        for user in DEMO_USERS:
            hashed = _hash_password(user["password"])
            await conn.execute(
                "INSERT INTO users (email, hashed_password, full_name, role, department) "
                "VALUES ($1, $2, $3, $4, $5)",
                user["email"],
                hashed,
                user["full_name"],
                user["role"],
                user["department"],
            )
            print(f"Created user: {user['email']}")

        print(f"{len(DEMO_USERS)} demo users seeded")
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# Leave balance seed data (Feature 16)
# ---------------------------------------------------------------------------

DEMO_LEAVE_DATA = [
    # admin@company.com — hr_admin — 25 annual, 15 sick, 5 personal
    {"email": "admin@company.com", "leave_type": "annual", "total_allocated": 25, "used": 5, "year": 2026},
    {"email": "admin@company.com", "leave_type": "sick", "total_allocated": 15, "used": 1, "year": 2026},
    {"email": "admin@company.com", "leave_type": "personal", "total_allocated": 5, "used": 2, "year": 2026},
    # john@company.com — employee — 20 annual, 10 sick, 3 personal
    {"email": "john@company.com", "leave_type": "annual", "total_allocated": 20, "used": 8, "year": 2026},
    {"email": "john@company.com", "leave_type": "sick", "total_allocated": 10, "used": 2, "year": 2026},
    {"email": "john@company.com", "leave_type": "personal", "total_allocated": 3, "used": 0, "year": 2026},
    # sarah@company.com — manager — 22 annual, 10 sick, 3 personal
    {"email": "sarah@company.com", "leave_type": "annual", "total_allocated": 22, "used": 15, "year": 2026},
    {"email": "sarah@company.com", "leave_type": "sick", "total_allocated": 10, "used": 3, "year": 2026},
    {"email": "sarah@company.com", "leave_type": "personal", "total_allocated": 3, "used": 3, "year": 2026},
    # priya@company.com — employee — 20 annual, 10 sick, 3 personal
    {"email": "priya@company.com", "leave_type": "annual", "total_allocated": 20, "used": 2, "year": 2026},
    {"email": "priya@company.com", "leave_type": "sick", "total_allocated": 10, "used": 0, "year": 2026},
    {"email": "priya@company.com", "leave_type": "personal", "total_allocated": 3, "used": 1, "year": 2026},
]


async def seed_leave_balances(db: AsyncSession | None = None) -> int:
    """Insert leave balance data for all demo users (idempotent).

    Uses ``ON CONFLICT DO NOTHING`` so repeated calls are safe.

    When *db* is provided (API path), uses the ORM :class:`LeaveRepository`.
    When *db* is ``None`` (startup path), uses raw asyncpg directly.

    Returns the number of rows inserted.
    """
    if db is not None:
        # API path — use ORM repository
        from app.repositories.leave import LeaveRepository

        repo = LeaveRepository(db)
        count = 0
        for entry in DEMO_LEAVE_DATA:
            email = entry["email"]
            # Look up user ID by email
            from sqlalchemy import select

            from app.models.models import User

            result = await db.execute(select(User).where(User.email == email))
            user = result.scalar_one_or_none()
            if user is None:
                continue

            seed_rows = [{
                "user_id": user.id,
                "leave_type": entry["leave_type"],
                "total_allocated": entry["total_allocated"],
                "used": entry["used"],
                "year": entry["year"],
            }]
            count += await repo.seed_leave_data(seed_rows)
        return count

    # Startup path — use raw asyncpg
    conn = await get_db_connection()
    try:
        count = 0
        for entry in DEMO_LEAVE_DATA:
            email = entry["email"]
            user_id = await conn.fetchval(
                "SELECT id FROM users WHERE email = $1", email
            )
            if user_id is None:
                continue
            await conn.execute(
                """
                INSERT INTO leave_balances (user_id, leave_type, total_allocated, used, year)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (user_id, leave_type, year) DO NOTHING
                """,
                user_id,
                entry["leave_type"],
                entry["total_allocated"],
                entry["used"],
                entry["year"],
            )
            count += 1

        print(f"{count} leave balance rows seeded")
        return count
    finally:
        await conn.close()
