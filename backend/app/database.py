import asyncpg
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings


# ---------------------------------------------------------------------------
# Connection string helper
# ---------------------------------------------------------------------------

def _build_database_url() -> str:
    """Build the async database URL from individual env vars if the full URL
    is not provided.

    Returns a ``postgresql+asyncpg://`` URL suitable for SQLAlchemy.
    """
    if settings.DATABASE_URL:
        return settings.DATABASE_URL
    return (
        f"postgresql+asyncpg://{settings.POSTGRES_USER}"
        f":{settings.POSTGRES_PASSWORD}"
        f"@db:5432/{settings.POSTGRES_DB}"
    )


def _build_asyncpg_url() -> str:
    """Return a plain ``postgresql://`` URL suitable for raw asyncpg connections.

    The SQLAlchemy driver prefix ``+asyncpg`` is stripped because asyncpg
    expects a scheme of ``postgresql`` or ``postgres`` only.
    """
    sqlalchemy_url = _build_database_url()
    return sqlalchemy_url.replace("+asyncpg", "")


# ---------------------------------------------------------------------------
# SQLAlchemy async engine & session factory
# ---------------------------------------------------------------------------

SQLALCHEMY_DATABASE_URL = _build_database_url()
ASYNCPG_URL = _build_asyncpg_url()

engine = create_async_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_pre_ping=settings.DB_POOL_PRE_PING,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ---------------------------------------------------------------------------
# FastAPI dependency generators
# ---------------------------------------------------------------------------

async def get_db():
    """Yield an async database session — use as a FastAPI ``Depends``."""
    async with AsyncSessionLocal() as session:
        yield session


async def get_db_connection() -> asyncpg.Connection:
    """Return a raw ``asyncpg`` connection for operations that need direct
    database access (DDL, vector operations, etc.)."""
    return await asyncpg.connect(ASYNCPG_URL)


# ---------------------------------------------------------------------------
# Table creation (raw SQL via asyncpg — no ORM DDL)
# ---------------------------------------------------------------------------

async def create_tables(conn: asyncpg.Connection) -> None:
    """Create all tables and indexes using raw SQL.

    Uses ``IF NOT EXISTS`` throughout — safe to call on every startup.
    """

    # -- users ------------------------------------------------------------------
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            email           VARCHAR(255) UNIQUE NOT NULL,
            hashed_password VARCHAR(255) NOT NULL,
            full_name       VARCHAR(255) NOT NULL,
            role            VARCHAR(50)  NOT NULL DEFAULT 'employee'
                            CHECK (role IN ('employee', 'manager', 'hr_admin')),
            department      VARCHAR(100) NOT NULL,
            is_active       BOOLEAN      NOT NULL DEFAULT TRUE,
            created_at      TIMESTAMPTZ  DEFAULT NOW(),
            updated_at      TIMESTAMPTZ  DEFAULT NOW()
        )
    """)
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_users_department ON users(department)"
    )

    # -- sessions ---------------------------------------------------------------
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id     UUID        NOT NULL REFERENCES users(id),
            is_active   BOOLEAN     NOT NULL DEFAULT TRUE,
            device_info JSONB,
            created_at  TIMESTAMPTZ DEFAULT NOW(),
            last_active TIMESTAMPTZ DEFAULT NOW(),
            expires_at  TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '24 hours')
        )
    """)
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_sessions_last_active ON sessions(last_active)"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions(expires_at)"
    )

    # -- messages ---------------------------------------------------------------
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id     UUID         NOT NULL REFERENCES sessions(id),
            user_id        UUID         NOT NULL REFERENCES users(id),
            role           VARCHAR(20)  NOT NULL
                           CHECK (role IN ('user', 'assistant')),
            content        TEXT         NOT NULL,
            sources        JSONB,
            confidence     VARCHAR(20)
                           CHECK (confidence IN ('high', 'medium', 'low', 'none')),
            tokens_used    INTEGER,
            classification VARCHAR(30),
            created_at     TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id)"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_messages_user_id ON messages(user_id)"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at)"
    )

    # -- feedback ---------------------------------------------------------------
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            message_id UUID        NOT NULL REFERENCES messages(id),
            user_id    UUID        NOT NULL REFERENCES users(id),
            rating     VARCHAR(10) NOT NULL
                       CHECK (rating IN ('positive', 'negative')),
            reason     VARCHAR(50),
            comment    TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_feedback_message_id ON feedback(message_id)"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_feedback_user_id ON feedback(user_id)"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_feedback_rating ON feedback(rating)"
    )

    # -- system_logs (Feature 11) -----------------------------------------------
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS system_logs (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            timestamp    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            level        VARCHAR(20)  NOT NULL,
            component    VARCHAR(50)  NOT NULL,
            event        VARCHAR(100) NOT NULL,
            user_id      UUID REFERENCES users(id),
            session_id   UUID REFERENCES sessions(id),
            message_id   UUID REFERENCES messages(id),
            details      JSONB,
            error_trace  TEXT
        )
    """)
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON system_logs(timestamp)"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_logs_level ON system_logs(level)"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_logs_component ON system_logs(component)"
    )

    # -- hr_documents -----------------------------------------------------------
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS hr_documents (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            content      TEXT          NOT NULL,
            embedding    VECTOR(768)   NOT NULL,
            source       VARCHAR(500)  NOT NULL,
            page         INTEGER,
            section      VARCHAR(500),
            chunk_index  INTEGER       NOT NULL,
            access_level VARCHAR(50)   NOT NULL DEFAULT 'all'
                         CHECK (access_level IN ('all', 'manager', 'hr_admin')),
            created_at   TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_hr_documents_source ON hr_documents(source)"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_hr_documents_access_level ON hr_documents(access_level)"
    )

    # -- ivfflat vector index (pgvector-dependent) ------------------------------
    try:
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_hr_documents_embedding
            ON hr_documents
            USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 100)
        """)
        print("Vector index (ivfflat) created on hr_documents.embedding")
    except Exception as exc:
        print(f"WARNING — could not create vector index: {exc}")


# ---------------------------------------------------------------------------
# Database initialization (called on startup)
# ---------------------------------------------------------------------------

async def init_db() -> None:
    """Idempotent initialisation — safe to call on every application startup.

    1. Enables the ``vector`` extension.
    2. Creates all tables and indexes (if they do not exist).
    3. Runs additive schema migrations (new columns, FK cascades).
    """
    conn = await get_db_connection()
    try:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        print("pgvector extension ready")

        await create_tables(conn)
        await _run_migrations(conn)
        print("Database initialized successfully")
    except Exception as exc:
        print(f"Database initialization failed: {exc}")
        raise
    finally:
        await conn.close()


async def _run_migrations(conn: asyncpg.Connection) -> None:
    """Additive schema migrations — safe to call on every startup.

    Each statement uses ``IF NOT EXISTS`` or a DO-block guard so it is
    idempotent across restarts.
    """

    # -- Session schema additions (Feature 9) ---------------------------------
    await conn.execute(
        "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS title VARCHAR(255)"
    )
    await conn.execute(
        "ALTER TABLE sessions "
        "ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW()"
    )

    # -- FK cascade: messages.session_id -> sessions.id -----------------------
    await conn.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.table_constraints
                WHERE constraint_name = 'messages_session_id_fkey'
                  AND table_name = 'messages'
            ) THEN
                ALTER TABLE messages DROP CONSTRAINT messages_session_id_fkey;
            END IF;
        END $$;
    """)
    await conn.execute("""
        ALTER TABLE messages
        ADD CONSTRAINT messages_session_id_fkey
        FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
    """)

    # -- FK cascade: feedback.message_id -> messages.id -----------------------
    await conn.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.table_constraints
                WHERE constraint_name = 'feedback_message_id_fkey'
                  AND table_name = 'feedback'
            ) THEN
                ALTER TABLE feedback DROP CONSTRAINT feedback_message_id_fkey;
            END IF;
        END $$;
    """)
    await conn.execute("""
        ALTER TABLE feedback
        ADD CONSTRAINT feedback_message_id_fkey
        FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
    """)

    # -- Feature 11: processing_time_ms column on messages ---------------------
    await conn.execute(
        "ALTER TABLE messages ADD COLUMN IF NOT EXISTS processing_time_ms DOUBLE PRECISION"
    )

    print("Database migrations applied successfully")
