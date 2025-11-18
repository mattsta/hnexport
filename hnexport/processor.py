"""Data processor for splitting HackerNews bundles by type and time.

Modernized version of split-to-parts.py with better error handling,
type hints, and logging.
"""

import html
import json
import lzma
from pathlib import Path
from typing import Any, Optional

from .config import config
from .logger import logger


class BundleProcessor:
    """Process downloaded HN bundles and split by type, user, and time."""

    # ASCII record separator for delimited output
    RECORD_SEPARATOR = "\x1e"

    def __init__(
        self,
        input_dir: Optional[Path] = None,
        output_dir: Optional[Path] = None,
        split_duration_months: Optional[int] = None,
    ) -> None:
        """Initialize the processor.

        Args:
            input_dir: Directory containing downloaded bundles
            output_dir: Directory for split output
            split_duration_months: Months per time bucket (default: 3)
        """
        self.input_dir = input_dir or config.storage.output_dir / "item"
        self.output_dir = output_dir or Path("split")
        self.split_duration_months = split_duration_months or config.storage.monthly_split_duration

        # Calculate split duration in seconds (3 months ≈ 52/4 weeks)
        import datetime
        self.split_duration_seconds = datetime.timedelta(
            weeks=52 / (12 / self.split_duration_months)
        ).total_seconds()

        logger.info(
            f"Initialized BundleProcessor (input={self.input_dir}, "
            f"output={self.output_dir}, split={self.split_duration_months} months)"
        )

    def _get_output_dir(self, type_or_path: str) -> Path:
        """Get output directory for a type or user path.

        Args:
            type_or_path: Item type (e.g., 'comment') or path (e.g., 'user/alice')

        Returns:
            Path to output directory
        """
        dir_path = self.output_dir / type_or_path
        dir_path.mkdir(parents=True, exist_ok=True)
        return dir_path

    def _write_entry(
        self,
        item_type: str,
        time_bucket: int,
        username: str,
        content: str,
    ) -> None:
        """Write an entry to type and user directories.

        Args:
            item_type: Type of item (story, comment, job, poll, pollopt)
            time_bucket: Time bucket number
            username: Author's username
            content: Text content to write
        """
        # Write to type directory (global and time-bucketed)
        type_dir = self._get_output_dir(item_type)
        self._append_to_files(
            type_dir,
            time_bucket,
            content,
        )

        # Write to user directory (global and time-bucketed)
        user_dir = self._get_output_dir(f"user/{username}")
        self._append_to_files(
            user_dir,
            time_bucket,
            content,
        )

    def _append_to_files(
        self,
        directory: Path,
        time_bucket: int,
        content: str,
    ) -> None:
        """Append content to global and time-bucketed files.

        Args:
            directory: Target directory
            time_bucket: Time bucket number
            content: Content to append
        """
        # Write to global file
        global_file = directory / "global"
        with global_file.open("at") as f:
            f.write(content)
            f.write(self.RECORD_SEPARATOR)

        # Write to time-bucketed file
        bucket_file = directory / str(time_bucket)
        with bucket_file.open("at") as f:
            f.write(content)
            f.write(self.RECORD_SEPARATOR)

    def _extract_bundle_start_id(self, filename: str) -> int:
        """Extract starting ID from bundle filename.

        Args:
            filename: Bundle filename (e.g., '0-99.xz')

        Returns:
            Starting ID
        """
        return int(filename.split("-")[0])

    def _process_bundle(self, bundle_path: Path) -> tuple[int, int, int]:
        """Process a single bundle file.

        Args:
            bundle_path: Path to .xz bundle file

        Returns:
            Tuple of (processed_count, skipped_count, error_count)
        """
        logger.info(f"Processing bundle: {bundle_path.name}")

        processed = 0
        skipped = 0
        errors = 0

        try:
            # Read and decompress bundle
            with lzma.open(bundle_path, "rt") as f:
                content = f.read()

            # Parse concatenated JSON objects into array
            # Original format: {"id":1}{"id":2} -> [{"id":1},{"id":2}]
            list_delim = '"},{"'.join(content.split('"}{"'))
            list_wrap = f"[{list_delim}]"
            items = json.loads(list_wrap)

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse bundle {bundle_path.name}: {e}")
            return 0, 0, 1
        except Exception as e:
            logger.error(f"Failed to read bundle {bundle_path.name}: {e}")
            return 0, 0, 1

        # Process each item
        for item in items:
            try:
                # Skip deleted items
                if item.get("deleted") or item.get("dead"):
                    skipped += 1
                    continue

                # Extract required fields
                item_type = item.get("type")
                item_time = item.get("time")
                username = item.get("by")

                if not all([item_type, item_time, username]):
                    skipped += 1
                    continue

                # Calculate time bucket
                time_bucket = int(item_time // self.split_duration_seconds)

                # Extract text content (prioritize 'text', fall back to 'title')
                content = item.get("text") or item.get("title")
                if not content:
                    skipped += 1
                    continue

                # Unescape HTML entities
                content = html.unescape(content)

                # Write entry
                self._write_entry(item_type, time_bucket, username, content)
                processed += 1

            except Exception as e:
                logger.error(f"Error processing item in {bundle_path.name}: {e}")
                logger.debug(f"Item data: {item}")
                errors += 1

        return processed, skipped, errors

    def process_all_bundles(self) -> dict[str, int]:
        """Process all bundles in the input directory.

        Returns:
            Dictionary of statistics
        """
        # Find all .xz bundle files
        bundle_files = sorted(
            self.input_dir.glob("*.xz"),
            key=lambda p: self._extract_bundle_start_id(p.name),
        )

        if not bundle_files:
            logger.warning(f"No bundle files found in {self.input_dir}")
            return {"bundles": 0, "processed": 0, "skipped": 0, "errors": 0}

        logger.info(f"Found {len(bundle_files)} bundles to process")

        # Process each bundle
        total_processed = 0
        total_skipped = 0
        total_errors = 0

        for bundle_path in bundle_files:
            processed, skipped, errors = self._process_bundle(bundle_path)

            total_processed += processed
            total_skipped += skipped
            total_errors += errors

            # Log progress
            if len(bundle_files) > 10 and (bundle_files.index(bundle_path) + 1) % 10 == 0:
                logger.info(
                    f"Progress: {bundle_files.index(bundle_path) + 1}/{len(bundle_files)} bundles, "
                    f"{total_processed:,} items processed"
                )

        stats = {
            "bundles": len(bundle_files),
            "processed": total_processed,
            "skipped": total_skipped,
            "errors": total_errors,
        }

        logger.info(
            f"Processing complete:\n"
            f"  Bundles: {stats['bundles']:,}\n"
            f"  Processed: {stats['processed']:,}\n"
            f"  Skipped: {stats['skipped']:,}\n"
            f"  Errors: {stats['errors']:,}"
        )

        return stats


def process_bundles(
    input_dir: Optional[Path] = None,
    output_dir: Optional[Path] = None,
) -> dict[str, int]:
    """Convenience function to process bundles.

    Args:
        input_dir: Directory containing downloaded bundles
        output_dir: Directory for split output

    Returns:
        Processing statistics
    """
    processor = BundleProcessor(input_dir, output_dir)
    return processor.process_all_bundles()
