"""HNexport - High-performance async HackerNews data export tool.

Modern async/await implementation using httpx for downloading and archiving
HackerNews content.
"""

from .client import HackerNewsClient
from .config import Config, config
from .downloader import HNDownloader, download_with_multiprocessing
from .exceptions import (
    APIError,
    ConfigurationError,
    HNExportError,
    ItemNotFoundError,
    NetworkError,
    RateLimitError,
    RetryExhaustedError,
    StorageError,
)
from .logger import logger, setup_logger
from .models import DownloadStats, HNItem, HNUser

__version__ = "2.0.0"
__author__ = "Matt Stancliff"

__all__ = [
    # Client
    "HackerNewsClient",
    # Downloader
    "HNDownloader",
    "download_with_multiprocessing",
    # Configuration
    "Config",
    "config",
    # Models
    "HNItem",
    "HNUser",
    "DownloadStats",
    # Exceptions
    "HNExportError",
    "APIError",
    "RateLimitError",
    "ItemNotFoundError",
    "NetworkError",
    "StorageError",
    "ConfigurationError",
    "RetryExhaustedError",
    # Logging
    "logger",
    "setup_logger",
    # Metadata
    "__version__",
    "__author__",
]
