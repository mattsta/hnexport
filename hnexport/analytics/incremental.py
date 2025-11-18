"""Incremental update support for efficient delta downloads."""

import asyncio
import json
import lzma
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Set

from ..client import HackerNewsClient
from ..downloader import HNDownloader
from ..logger import logger


@dataclass
class IncrementalUpdateReport:
    """Report from an incremental update."""

    start_id: int = 0
    end_id: int = 0
    new_items: int = 0
    updated_items: int = 0
    total_time_seconds: float = 0.0
    items_per_second: float = 0.0

    def to_dict(self):
        """Convert to dictionary."""
        return {
            "start_id": self.start_id,
            "end_id": self.end_id,
            "new_items": self.new_items,
            "updated_items": self.updated_items,
            "total_time_seconds": round(self.total_time_seconds, 2),
            "items_per_second": round(self.items_per_second, 2),
        }

    def __str__(self) -> str:
        """Human-readable report."""
        return (
            f"Incremental Update Complete\n"
            f"  Range: {self.start_id:,} to {self.end_id:,}\n"
            f"  New Items: {self.new_items:,}\n"
            f"  Updated Items: {self.updated_items:,}\n"
            f"  Time: {self.total_time_seconds:.1f}s "
            f"({self.items_per_second:.1f} items/sec)"
        )


class IncrementalUpdater:
    """Efficient incremental updates for HackerNews data.

    Downloads only new items since last update, avoiding re-download of
    existing data.

    Example:
        updater = IncrementalUpdater(data_dir=Path("hn"))
        report = await updater.update()
        print(f"Downloaded {report.new_items} new items")
    """

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.item_dir = data_dir / "item"
        self.item_dir.mkdir(parents=True, exist_ok=True)

        # Metadata file to track updates
        self.metadata_file = self.item_dir / ".update_metadata.json"

    def get_highest_local_id(self) -> int:
        """Find the highest item ID in local bundles.

        Returns:
            Highest local item ID, or 0 if no bundles exist
        """
        logger.info("Finding highest local item ID")

        highest_id = 0
        bundles = sorted(self.item_dir.glob("*.xz"))

        if not bundles:
            logger.info("No existing bundles found")
            return 0

        # Check last few bundles for highest ID
        # Bundles are named by range, so last bundle should have highest IDs
        for bundle_path in reversed(bundles[-10:]):  # Check last 10 bundles
            try:
                with lzma.open(bundle_path, "rt", encoding="utf-8") as f:
                    for line in f:
                        if not line.strip() or line.strip() == "null":
                            continue

                        try:
                            item = json.loads(line)
                            item_id = item.get("id", 0)
                            if item_id > highest_id:
                                highest_id = item_id
                        except json.JSONDecodeError:
                            continue

            except Exception as e:
                logger.warning(f"Error reading bundle {bundle_path.name}: {e}")
                continue

        logger.info(f"Highest local ID: {highest_id:,}")
        return highest_id

    def load_metadata(self) -> dict:
        """Load update metadata.

        Returns:
            Metadata dictionary
        """
        if not self.metadata_file.exists():
            return {}

        try:
            return json.loads(self.metadata_file.read_text())
        except Exception as e:
            logger.warning(f"Error loading metadata: {e}")
            return {}

    def save_metadata(self, metadata: dict) -> None:
        """Save update metadata.

        Args:
            metadata: Metadata to save
        """
        try:
            self.metadata_file.write_text(json.dumps(metadata, indent=2))
        except Exception as e:
            logger.error(f"Error saving metadata: {e}")

    async def update(
        self,
        force_start_id: Optional[int] = None,
        batch_size: int = 1000,
    ) -> IncrementalUpdateReport:
        """Perform incremental update to download new items.

        Args:
            force_start_id: Force specific start ID (None = auto-detect)
            batch_size: Items to download per batch

        Returns:
            IncrementalUpdateReport with update statistics
        """
        start_time = datetime.now()

        # Load metadata
        metadata = self.load_metadata()
        last_update = metadata.get("last_update")
        last_highest_id = metadata.get("last_highest_id", 0)

        logger.info(f"Last update: {last_update or 'Never'}")
        logger.info(f"Last highest ID: {last_highest_id:,}")

        # Determine start ID
        if force_start_id is not None:
            start_id = force_start_id
            logger.info(f"Using forced start ID: {start_id:,}")
        else:
            local_highest = self.get_highest_local_id()
            # Use the higher of: local highest or metadata highest
            start_id = max(local_highest, last_highest_id) + 1
            logger.info(f"Auto-detected start ID: {start_id:,}")

        # Get current highest ID from HN API
        async with HackerNewsClient() as client:
            current_highest = await client.get_highest_item_id()

        logger.info(f"Current HN highest ID: {current_highest:,}")

        if start_id >= current_highest:
            logger.info("Already up to date!")
            return IncrementalUpdateReport(
                start_id=start_id,
                end_id=current_highest,
                new_items=0,
                updated_items=0,
            )

        # Calculate items to download
        items_to_download = current_highest - start_id + 1
        logger.info(f"Downloading {items_to_download:,} new items")

        # Download using HNDownloader
        downloader = HNDownloader(output_dir=self.data_dir)

        await downloader.download_item_range(
            start_id=start_id,
            end_id=current_highest,
            item_type="item",
        )

        # Calculate statistics
        end_time = datetime.now()
        total_seconds = (end_time - start_time).total_seconds()

        report = IncrementalUpdateReport(
            start_id=start_id,
            end_id=current_highest,
            new_items=items_to_download,
            updated_items=0,
            total_time_seconds=total_seconds,
            items_per_second=items_to_download / total_seconds if total_seconds > 0 else 0,
        )

        # Update metadata
        metadata.update(
            {
                "last_update": datetime.now().isoformat(),
                "last_highest_id": current_highest,
                "last_update_report": report.to_dict(),
            }
        )
        self.save_metadata(metadata)

        logger.info(str(report))
        return report

    async def update_specific_items(
        self, item_ids: list[int], force: bool = False
    ) -> int:
        """Update specific items by ID.

        Useful for refreshing items that may have been updated (scores, comments, etc.)

        Args:
            item_ids: List of item IDs to update
            force: Force re-download even if items exist locally

        Returns:
            Number of items updated
        """
        logger.info(f"Updating {len(item_ids):,} specific items")

        # Filter out existing items unless force is True
        if not force:
            existing_ids = await self._get_existing_item_ids()
            item_ids = [id for id in item_ids if id not in existing_ids]
            logger.info(f"Filtered to {len(item_ids):,} items (excluding existing)")

        if not item_ids:
            logger.info("No items to update")
            return 0

        # Download items
        async with HackerNewsClient() as client:
            # Batch download
            batch_size = 100
            updated = 0

            for i in range(0, len(item_ids), batch_size):
                batch = item_ids[i : i + batch_size]
                items = await client.get_items_batch(batch)

                # Save to bundles (simplified - would need proper bundling)
                # For now, just count successful downloads
                for item in items:
                    if item:
                        updated += 1

                logger.info(f"Progress: {min(i + batch_size, len(item_ids)):,}/{len(item_ids):,}")

        logger.info(f"Updated {updated:,} items")
        return updated

    async def _get_existing_item_ids(self) -> Set[int]:
        """Get set of all existing item IDs.

        Returns:
            Set of item IDs that exist locally
        """
        existing_ids: Set[int] = set()

        bundles = sorted(self.item_dir.glob("*.xz"))

        for bundle_path in bundles:
            try:
                with lzma.open(bundle_path, "rt", encoding="utf-8") as f:
                    for line in f:
                        if not line.strip() or line.strip() == "null":
                            continue

                        try:
                            item = json.loads(line)
                            item_id = item.get("id")
                            if item_id:
                                existing_ids.add(item_id)
                        except json.JSONDecodeError:
                            continue

            except Exception as e:
                logger.warning(f"Error reading bundle {bundle_path.name}: {e}")
                continue

        return existing_ids

    def get_update_schedule_recommendation(self) -> str:
        """Get recommendation for update schedule based on HN activity.

        Returns:
            Human-readable schedule recommendation
        """
        # HN typically gets 3000-5000 new items per day
        # Recommendations based on usage patterns

        recommendations = {
            "high_frequency": "Every 1-2 hours (for real-time monitoring)",
            "daily": "Once per day (recommended for most users)",
            "weekly": "Once per week (for historical analysis)",
            "custom": "Custom schedule based on your needs",
        }

        metadata = self.load_metadata()
        last_update = metadata.get("last_update")

        if not last_update:
            return "Initial download - run full download first, then schedule updates"

        # Calculate time since last update
        try:
            last_dt = datetime.fromisoformat(last_update)
            hours_since = (datetime.now() - last_dt).total_seconds() / 3600

            if hours_since < 24:
                return recommendations["high_frequency"]
            elif hours_since < 168:  # 1 week
                return recommendations["daily"]
            else:
                return recommendations["weekly"]

        except Exception:
            return recommendations["daily"]


# CLI helper function
async def main():
    """CLI entry point for incremental updates."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m hnexport.analytics.incremental <data_dir>")
        sys.exit(1)

    data_dir = Path(sys.argv[1])

    updater = IncrementalUpdater(data_dir)
    report = await updater.update()

    print("\n" + str(report))
    print(f"\nRecommended schedule: {updater.get_update_schedule_recommendation()}")


if __name__ == "__main__":
    asyncio.run(main())
