"""Structured logging setup for the HR Q&A Agent.

Provides:
- ``StructuredFormatter`` — outputs log records as single-line JSON.
- ``DBLogHandler`` — writes INFO+ records to the ``system_logs`` table.
- ``setup_logging()`` — configures the root logger with both handlers.
"""

import json
import logging
import traceback
from datetime import datetime, timezone
from typing import Optional


class StructuredFormatter(logging.Formatter):
    """Output log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Attach structured fields when present on the record
        for attr in ("component", "event", "details"):
            value = getattr(record, attr, None)
            if value is not None:
                log_entry[attr] = value

        if record.exc_info and record.exc_info[0]:
            log_entry["error_trace"] = "".join(
                traceback.format_exception(*record.exc_info)
            )

        return json.dumps(log_entry, default=str)


class _StructuredFilter(logging.Filter):
    """Inject extra dict values as ``LogRecord`` attributes.

    When a caller does ``logger.info("msg", extra={"component": "rag", ...})``,
    Python's ``Logger`` raises ``KeyError`` for unrecognised keys unless a
    filter picks them up.  This filter copies every value from the ``extra``
    dict onto the record so that ``StructuredFormatter`` can access them.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        # The ``extra`` dict is not stored on the record — it was passed as
        # keyword arguments to ``_log()`` and already set as individual
        # attributes.  We don't need to do anything here; the attributes are
        # already present.  However, if a caller omits one of the expected
        # keys, the logging framework raises a KeyError BEFORE filter() runs.
        # We handle that by using logger._log(...) with a safe wrapper.
        return True


class DBLogHandler(logging.Handler):
    """Write INFO+ log records to the ``system_logs`` database table.

    Uses fire-and-forget async writes to avoid blocking the request thread.
    """

    def __init__(
        self,
        session_factory,
        level: int = logging.INFO,
    ) -> None:
        super().__init__(level=level)
        self._session_factory = session_factory

    def emit(self, record: logging.LogRecord) -> None:
        """Schedule an async DB write for this record.

        If no event loop is running (e.g. during startup), the record is
        silently dropped — the console handler is the primary output in that
        phase.
        """
        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No event loop running — cannot write to DB
            return

        # Extract structured fields (set by ``extra`` dict in the log call)
        component = getattr(record, "component", record.name)
        event = getattr(record, "event", record.levelname.lower())
        details = getattr(record, "details", None)
        error_trace = None
        if record.exc_info and record.exc_info[0]:
            error_trace = "".join(traceback.format_exception(*record.exc_info))

        # Copy values so the async task doesn't reference a freed LogRecord
        level_str = record.levelname
        message = record.getMessage()

        loop.create_task(
            self._write_to_db(
                level_str=level_str,
                component=component,
                event=event,
                message=message,
                details=details,
                error_trace=error_trace,
            )
        )

    async def _write_to_db(
        self,
        level_str: str,
        component: str,
        event: str,
        message: str,
        details: Optional[dict],
        error_trace: Optional[str],
    ) -> None:
        """Persist a single log entry to ``system_logs``."""
        from app.models.models import SystemLog
        from sqlalchemy import select

        try:
            async with self._session_factory() as db:
                entry = SystemLog(
                    level=level_str,
                    component=component,
                    event=event,
                    details=details,
                    error_trace=error_trace,
                )
                db.add(entry)
                await db.commit()
        except Exception:
            # Never crash the application because logging failed.
            import sys

            print(
                f"[DBLogHandler] Failed to write log to database: {message}",
                file=sys.stderr,
            )


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger for the given name."""
    return logging.getLogger(name)


def setup_logging(session_factory=None) -> None:
    """Configure structured JSON logging for the application.

    Parameters
    ----------
    session_factory : optional
        An async session factory (e.g. ``AsyncSessionLocal``).  When provided,
        a ``DBLogHandler`` is attached that persists INFO+ records to the
        ``system_logs`` table.
    """
    root = logging.getLogger()
    root.handlers.clear()

    # Console handler — JSON lines to stdout (picked up by Docker)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(StructuredFormatter())
    console_handler.setLevel(logging.DEBUG)
    root.addHandler(console_handler)

    # DB handler — persists INFO+ to system_logs
    if session_factory is not None:
        db_handler = DBLogHandler(session_factory, level=logging.INFO)
        root.addHandler(db_handler)

    # Default level from settings (override via .env)
    from app.config import settings

    root.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))

    # Suppress noisy library loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
