"""Configuration management for HNexport.

This module provides centralized configuration with environment variable support
and type-safe settings using dataclasses.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class APIConfig:
    """Configuration for HackerNews API access."""

    base_url: str = "https://hacker-news.firebaseio.com/v0"
    highest_item_endpoint: str = "/maxitem.json"
    item_endpoint_template: str = "/item/{item_id}.json"
    user_endpoint_template: str = "/user/{username}.json"

    # Timeout settings
    connect_timeout: float = 5.0
    read_timeout: float = 10.0

    # Retry settings
    max_retries: int = 7
    backoff_factor: float = 0.5

    @property
    def timeout(self) -> tuple[float, float]:
        """Return timeout as (connect, read) tuple for httpx."""
        return (self.connect_timeout, self.read_timeout)


@dataclass
class ConcurrencyConfig:
    """Configuration for concurrent operations."""

    # Async HTTP concurrency (semaphore limit)
    max_concurrent_requests: int = field(
        default_factory=lambda: int(os.getenv("HNEXPORT_MAX_CONCURRENT", "50"))
    )

    # Multiprocessing settings
    multiprocessing_workers: Optional[int] = field(
        default_factory=lambda: (
            int(os.getenv("HNEXPORT_WORKERS", "0")) or None
        )
    )

    # Items per worker process
    items_per_worker: int = 20_000

    # Batch size for fetching
    batch_size: int = 100

    # Groups of batches to pipeline
    pipeline_groups: int = 10


@dataclass
class StorageConfig:
    """Configuration for data storage."""

    # Output directory
    output_dir: Path = field(
        default_factory=lambda: Path(os.getenv("HNEXPORT_OUTPUT_DIR", "hn"))
    )

    # Bundle size (items per compressed file)
    bundle_size: int = 100

    # Compression settings
    compression_preset: int = 9  # lzma compression level (0-9)

    # Split processing settings
    monthly_split_duration: int = 3  # months per split


@dataclass
class LoggingConfig:
    """Configuration for logging."""

    level: str = field(
        default_factory=lambda: os.getenv("HNEXPORT_LOG_LEVEL", "INFO")
    )

    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # Enable file logging
    log_to_file: bool = field(
        default_factory=lambda: os.getenv("HNEXPORT_LOG_FILE", "").lower() == "true"
    )

    log_file: Optional[Path] = field(
        default_factory=lambda: (
            Path(os.getenv("HNEXPORT_LOG_FILE_PATH", "hnexport.log"))
            if os.getenv("HNEXPORT_LOG_FILE", "").lower() == "true"
            else None
        )
    )


@dataclass
class Config:
    """Main configuration container."""

    api: APIConfig = field(default_factory=APIConfig)
    concurrency: ConcurrencyConfig = field(default_factory=ConcurrencyConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    @classmethod
    def from_env(cls) -> "Config":
        """Create configuration from environment variables."""
        return cls()

    def __repr__(self) -> str:
        """Return a readable representation of the config."""
        return (
            f"Config(\n"
            f"  max_concurrent={self.concurrency.max_concurrent_requests},\n"
            f"  workers={self.concurrency.multiprocessing_workers or 'auto'},\n"
            f"  output_dir={self.storage.output_dir},\n"
            f"  log_level={self.logging.level}\n"
            f")"
        )


# Global configuration instance
config = Config.from_env()
