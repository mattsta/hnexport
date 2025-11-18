"""Custom exceptions for HNexport.

Specific exception types for better error handling and recovery.
"""


class HNExportError(Exception):
    """Base exception for all HNexport errors."""

    pass


class APIError(HNExportError):
    """Error communicating with HackerNews API."""

    pass


class RateLimitError(APIError):
    """API rate limit exceeded."""

    pass


class ItemNotFoundError(APIError):
    """Requested item does not exist."""

    pass


class NetworkError(HNExportError):
    """Network-related error during download."""

    pass


class StorageError(HNExportError):
    """Error writing to storage."""

    pass


class ConfigurationError(HNExportError):
    """Invalid configuration."""

    pass


class RetryExhaustedError(HNExportError):
    """All retry attempts have been exhausted."""

    def __init__(self, attempts: int, last_error: Exception) -> None:
        """Initialize with retry count and last error."""
        self.attempts = attempts
        self.last_error = last_error
        super().__init__(
            f"Exhausted {attempts} retry attempts. Last error: {last_error}"
        )
