"""Custom exception classes for the application."""


class AppException(Exception):
    """Base application exception with an HTTP status code."""

    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class NotFoundException(AppException):
    def __init__(self, entity: str, entity_id: str | None = None):
        msg = f"{entity} not found"
        if entity_id:
            msg += f": {entity_id}"
        super().__init__(msg, status_code=404)


class DuplicateException(AppException):
    def __init__(self, entity: str, field: str, value: str):
        msg = f"{entity} with {field} '{value}' already exists"
        super().__init__(msg, status_code=409)


class UnauthorizedException(AppException):
    def __init__(self, detail: str = "Could not validate credentials"):
        super().__init__(detail, status_code=401)


class ForbiddenException(AppException):
    def __init__(self, detail: str = "Access denied"):
        super().__init__(detail, status_code=403)


# ---------------------------------------------------------------------------
# Ingestion-specific exceptions
# ---------------------------------------------------------------------------


class IngestionError(AppException):
    """Base ingestion exception."""

    def __init__(self, message: str, status_code: int = 500):
        super().__init__(message, status_code)


class UnsupportedFileTypeError(IngestionError):
    def __init__(self, file_type: str, allowed: list[str]):
        msg = f"Unsupported file type: {file_type}. Allowed: {', '.join(allowed)}"
        super().__init__(msg, status_code=400)


class FileTooLargeError(IngestionError):
    def __init__(self, max_size_mb: int):
        msg = f"File size exceeds maximum of {max_size_mb}MB"
        super().__init__(msg, status_code=400)


class EmptyDocumentError(IngestionError):
    def __init__(self):
        super().__init__("Could not extract text from file", status_code=400)


class EmbeddingGenerationError(IngestionError):
    def __init__(self, attempts: int = 3):
        msg = f"Embedding generation failed after {attempts} attempts"
        super().__init__(msg, status_code=500)


class DocumentNotFoundError(IngestionError):
    def __init__(self, source: str):
        msg = f"Document not found: {source}"
        super().__init__(msg, status_code=404)
