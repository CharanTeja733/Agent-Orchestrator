from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str

    # Connection pooling
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_PRE_PING: bool = True

    # API keys & secrets
    GEMINI_API_KEY: str
    SECRET_KEY: str

    # Document ingestion
    MAX_FILE_SIZE_MB: int = 20
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200
    EMBEDDING_MODEL: str = "gemini-embedding-001"
    EMBEDDING_DIMENSIONS: int = 768
    EMBEDDING_BATCH_SIZE: int = 50
    ALLOWED_FILE_TYPES: list[str] = ["pdf", "docx", "txt"]

    # RAG Pipeline
    TOP_K_RETRIEVAL: int = 5
    MIN_RETRIEVAL_SCORE: float = 0.5
    HIGH_CONFIDENCE_THRESHOLD: float = 0.75
    MEDIUM_CONFIDENCE_THRESHOLD: float = 0.50
    LOW_CONFIDENCE_THRESHOLD: float = 0.30
    MAX_CONVERSATION_HISTORY: int = 6
    MAX_COMPLETION_TOKENS: int = 1024
    RESPONSE_TEMPERATURE: float = 0.3

    # Session Management (Feature 9)
    SESSION_EXPIRY_HOURS: int = 24
    SESSION_CLEANUP_AFTER_DAYS: int = 7
    SESSION_CLEANUP_INTERVAL_HOURS: int = 6
    MAX_CONVERSATION_HISTORY_CHARS: int = 2000
    AUTO_TITLE_MAX_LENGTH: int = 50

    # Logging (Feature 11)
    LOG_LEVEL: str = "INFO"
    LOG_RETENTION_DAYS: int = 30

    # Analytics (Feature 11)
    DEFAULT_STATS_PERIOD: str = "30d"

    # Feedback (Feature 11)
    FEEDBACK_REASONS: list[str] = [
        "incorrect_information",
        "incomplete_answer",
        "unclear_response",
        "irrelevant_sources",
        "outdated_information",
        "other",
    ]

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError(
                "SECRET_KEY must be at least 32 characters long for security"
            )
        return v

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
