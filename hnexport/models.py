"""Data models for HackerNews items and users.

Type-safe dataclasses representing HN API responses.
"""

from dataclasses import dataclass
from typing import Literal, Optional


ItemType = Literal["story", "comment", "job", "poll", "pollopt"]


@dataclass
class HNItem:
    """Represents a HackerNews item (story, comment, job, poll, or pollopt)."""

    id: int
    type: ItemType
    by: Optional[str] = None  # Username of the item's author
    time: Optional[int] = None  # Creation time (Unix timestamp)
    text: Optional[str] = None  # Comment, poll, or pollopt text (HTML)
    dead: Optional[bool] = None  # True if item is dead
    deleted: Optional[bool] = None  # True if item is deleted
    parent: Optional[int] = None  # Parent item ID
    poll: Optional[int] = None  # Poll ID (for pollopts)
    kids: Optional[list[int]] = None  # IDs of item's comments
    url: Optional[str] = None  # URL of the story
    score: Optional[int] = None  # Story or poll score
    title: Optional[str] = None  # Story or poll title
    parts: Optional[list[int]] = None  # Poll's related pollopts
    descendants: Optional[int] = None  # Total comment count

    @property
    def is_deleted(self) -> bool:
        """Check if item is deleted or dead."""
        return bool(self.deleted or self.dead)

    def to_dict(self) -> dict:
        """Convert to dictionary, excluding None values."""
        return {
            k: v
            for k, v in self.__dict__.items()
            if v is not None
        }


@dataclass
class HNUser:
    """Represents a HackerNews user profile."""

    id: str  # Username
    created: int  # Creation time (Unix timestamp)
    karma: int  # User's karma score
    about: Optional[str] = None  # User's self-description (HTML)
    submitted: Optional[list[int]] = None  # List of submitted item IDs

    def to_dict(self) -> dict:
        """Convert to dictionary, excluding None values."""
        return {
            k: v
            for k, v in self.__dict__.items()
            if v is not None
        }


@dataclass
class DownloadStats:
    """Statistics for a download session."""

    total_items: int = 0
    successful: int = 0
    failed: int = 0
    null_responses: int = 0
    bundles_created: int = 0
    start_time: float = 0.0
    end_time: float = 0.0

    @property
    def duration(self) -> float:
        """Return duration in seconds."""
        return self.end_time - self.start_time if self.end_time > 0 else 0.0

    @property
    def items_per_second(self) -> float:
        """Calculate download rate."""
        return self.successful / self.duration if self.duration > 0 else 0.0

    def __repr__(self) -> str:
        """Return a readable representation."""
        return (
            f"DownloadStats(total={self.total_items}, "
            f"successful={self.successful}, "
            f"failed={self.failed}, "
            f"rate={self.items_per_second:.2f}/s)"
        )
