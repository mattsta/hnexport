"""Real-time monitoring of new HackerNews items."""

import asyncio
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, List, Optional, Set

from ..client import HackerNewsClient
from ..logger import logger
from ..models import HNItem


@dataclass
class MonitorFilter:
    """Filter configuration for monitoring."""

    keywords: List[str] = field(default_factory=list)
    authors: List[str] = field(default_factory=list)
    domains: List[str] = field(default_factory=list)
    item_types: List[str] = field(default_factory=list)
    min_score: Optional[int] = None
    regex_pattern: Optional[str] = None

    def matches(self, item: HNItem) -> bool:
        """Check if item matches filter criteria.

        Args:
            item: Item to check

        Returns:
            True if item matches all filter criteria
        """
        # Check item type
        if self.item_types and item.type not in self.item_types:
            return False

        # Check author
        if self.authors and item.by not in self.authors:
            return False

        # Check score
        if self.min_score is not None and (item.score or 0) < self.min_score:
            return False

        # Check keywords in title/text
        if self.keywords:
            text = (item.title or "") + " " + (item.text or "")
            text_lower = text.lower()

            if not any(keyword.lower() in text_lower for keyword in self.keywords):
                return False

        # Check domains
        if self.domains and item.url:
            from urllib.parse import urlparse

            try:
                domain = urlparse(item.url).netloc
                if domain.startswith("www."):
                    domain = domain[4:]

                if not any(d in domain for d in self.domains):
                    return False
            except Exception:
                return False

        # Check regex pattern
        if self.regex_pattern:
            text = (item.title or "") + " " + (item.text or "")
            try:
                if not re.search(self.regex_pattern, text, re.IGNORECASE):
                    return False
            except re.error:
                logger.warning(f"Invalid regex pattern: {self.regex_pattern}")
                return False

        return True


@dataclass
class MonitorStats:
    """Statistics from monitoring session."""

    start_time: datetime = field(default_factory=datetime.now)
    items_checked: int = 0
    items_matched: int = 0
    highest_id_seen: int = 0
    errors: int = 0

    def __str__(self) -> str:
        """Human-readable stats."""
        runtime = (datetime.now() - self.start_time).total_seconds()
        rate = self.items_checked / runtime if runtime > 0 else 0

        return (
            f"Monitor Stats:\n"
            f"  Runtime: {runtime:.1f}s\n"
            f"  Items Checked: {self.items_checked:,} ({rate:.1f}/sec)\n"
            f"  Items Matched: {self.items_matched:,}\n"
            f"  Highest ID: {self.highest_id_seen:,}\n"
            f"  Errors: {self.errors}"
        )


class RealtimeMonitor:
    """Real-time monitor for new HackerNews items.

    Continuously polls the HN API for new items and triggers callbacks
    when items match specified filters.

    Example:
        def on_match(item):
            print(f"New item: {item.title}")

        monitor = RealtimeMonitor()
        monitor.add_filter(MonitorFilter(keywords=["python", "async"]))
        await monitor.start(on_match=on_match)
    """

    def __init__(
        self,
        poll_interval: float = 5.0,
        batch_size: int = 100,
    ):
        """Initialize monitor.

        Args:
            poll_interval: Seconds between polls for new items
            batch_size: Number of items to check per batch
        """
        self.poll_interval = poll_interval
        self.batch_size = batch_size
        self.filters: List[MonitorFilter] = []
        self.stats = MonitorStats()
        self._running = False
        self._seen_ids: Set[int] = set()

    def add_filter(self, filter: MonitorFilter) -> None:
        """Add a monitoring filter.

        Args:
            filter: Filter to add
        """
        self.filters.append(filter)
        logger.info(f"Added filter with {len(filter.keywords)} keywords")

    def clear_filters(self) -> None:
        """Clear all filters."""
        self.filters.clear()
        logger.info("Cleared all filters")

    async def start(
        self,
        on_match: Callable[[HNItem], None],
        duration_seconds: Optional[float] = None,
    ) -> MonitorStats:
        """Start monitoring for new items.

        Args:
            on_match: Callback function called when item matches filters
            duration_seconds: Optional duration to run (None = run indefinitely)

        Returns:
            MonitorStats when monitoring stops
        """
        logger.info(
            f"Starting real-time monitor (poll interval: {self.poll_interval}s, "
            f"filters: {len(self.filters)})"
        )

        self._running = True
        self.stats = MonitorStats()
        start_time = datetime.now()

        async with HackerNewsClient() as client:
            # Get starting point
            highest_id = await client.get_highest_item_id()
            self.stats.highest_id_seen = highest_id
            last_checked_id = highest_id

            logger.info(f"Starting from ID: {highest_id:,}")

            try:
                while self._running:
                    # Check if duration exceeded
                    if duration_seconds:
                        elapsed = (datetime.now() - start_time).total_seconds()
                        if elapsed >= duration_seconds:
                            logger.info(f"Duration limit reached ({duration_seconds}s)")
                            break

                    # Get current highest ID
                    try:
                        current_highest = await client.get_highest_item_id()
                    except Exception as e:
                        logger.error(f"Error getting highest ID: {e}")
                        self.stats.errors += 1
                        await asyncio.sleep(self.poll_interval)
                        continue

                    # Check for new items
                    if current_highest > last_checked_id:
                        new_item_ids = list(
                            range(last_checked_id + 1, current_highest + 1)
                        )
                        logger.debug(f"Found {len(new_item_ids)} new items")

                        # Process in batches
                        for i in range(0, len(new_item_ids), self.batch_size):
                            batch_ids = new_item_ids[i : i + self.batch_size]

                            try:
                                items = await client.get_items_batch(batch_ids)

                                for item in items:
                                    if not item:
                                        continue

                                    self.stats.items_checked += 1
                                    self._seen_ids.add(item.id)

                                    # Check if item matches any filter
                                    if self._matches_any_filter(item):
                                        self.stats.items_matched += 1
                                        try:
                                            on_match(item)
                                        except Exception as e:
                                            logger.error(f"Error in on_match callback: {e}")

                            except Exception as e:
                                logger.error(f"Error processing batch: {e}")
                                self.stats.errors += 1

                        last_checked_id = current_highest
                        self.stats.highest_id_seen = current_highest

                    # Wait before next poll
                    await asyncio.sleep(self.poll_interval)

            except KeyboardInterrupt:
                logger.info("Monitor stopped by user")
            except Exception as e:
                logger.error(f"Monitor error: {e}")
                self.stats.errors += 1
            finally:
                self._running = False

        logger.info(str(self.stats))
        return self.stats

    def stop(self) -> None:
        """Stop monitoring."""
        logger.info("Stopping monitor")
        self._running = False

    def _matches_any_filter(self, item: HNItem) -> bool:
        """Check if item matches any filter.

        Args:
            item: Item to check

        Returns:
            True if item matches at least one filter, or if no filters are set
        """
        # If no filters, match everything
        if not self.filters:
            return True

        # Check each filter
        for filter in self.filters:
            if filter.matches(item):
                return True

        return False

    async def get_recent_matches(
        self, lookback_items: int = 100
    ) -> List[HNItem]:
        """Get recent items that match filters (historical check).

        Args:
            lookback_items: Number of recent items to check

        Returns:
            List of matching items
        """
        logger.info(f"Checking last {lookback_items} items for matches")

        matches = []

        async with HackerNewsClient() as client:
            highest_id = await client.get_highest_item_id()
            start_id = max(1, highest_id - lookback_items + 1)

            item_ids = list(range(start_id, highest_id + 1))

            # Process in batches
            for i in range(0, len(item_ids), self.batch_size):
                batch_ids = item_ids[i : i + self.batch_size]

                try:
                    items = await client.get_items_batch(batch_ids)

                    for item in items:
                        if item and self._matches_any_filter(item):
                            matches.append(item)

                except Exception as e:
                    logger.error(f"Error processing batch: {e}")

        logger.info(f"Found {len(matches)} matching items")
        return matches


# CLI helper
async def main():
    """CLI entry point for monitor."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m hnexport.analytics.monitor <keywords...>")
        print("Example: python -m hnexport.analytics.monitor python async")
        sys.exit(1)

    keywords = sys.argv[1:]

    def on_match(item: HNItem):
        """Print matching items."""
        print(f"\n{'=' * 60}")
        print(f"[{item.type}] {item.title or item.text[:50]}")
        print(f"By: {item.by} | Score: {item.score}")
        if item.url:
            print(f"URL: {item.url}")
        print(f"HN: https://news.ycombinator.com/item?id={item.id}")

    monitor = RealtimeMonitor(poll_interval=10.0)
    monitor.add_filter(MonitorFilter(keywords=keywords))

    print(f"Monitoring HackerNews for keywords: {', '.join(keywords)}")
    print("Press Ctrl+C to stop\n")

    await monitor.start(on_match=on_match)


if __name__ == "__main__":
    asyncio.run(main())
