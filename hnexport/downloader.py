"""Async downloader for HackerNews items.

Modern async/await implementation replacing the old thread-based approach.
"""

import asyncio
import json
import lzma
import os
import time
from pathlib import Path
from typing import Optional

from .client import HackerNewsClient
from .config import config
from .logger import logger
from .models import DownloadStats


class HNDownloader:
    """High-performance async downloader for HackerNews content.

    Features:
    - True async/await concurrency (not thread-based)
    - Automatic bundling and compression
    - Progress tracking and statistics
    - Resume capability (skips existing bundles)
    - File timestamps set to last item's creation time
    """

    def __init__(
        self,
        output_dir: Optional[Path] = None,
        bundle_size: Optional[int] = None,
    ) -> None:
        """Initialize the downloader.

        Args:
            output_dir: Output directory for downloaded data
            bundle_size: Number of items per compressed bundle
        """
        self.output_dir = output_dir or config.storage.output_dir
        self.bundle_size = bundle_size or config.storage.bundle_size
        self.stats = DownloadStats()

        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Initialized HNDownloader (output_dir={self.output_dir})")

    def _bundle_path(self, item_type: str, start_id: int) -> Path:
        """Get the path for a bundle file.

        Args:
            item_type: Type of items (e.g., 'item', 'user')
            start_id: Starting ID for the bundle

        Returns:
            Path to the bundle file
        """
        type_dir = self.output_dir / item_type
        type_dir.mkdir(parents=True, exist_ok=True)

        end_id = start_id + self.bundle_size - 1
        return type_dir / f"{start_id}-{end_id}.xz"

    def _bundle_exists(self, item_type: str, start_id: int) -> bool:
        """Check if a bundle already exists.

        Args:
            item_type: Type of items
            start_id: Starting ID for the bundle

        Returns:
            True if bundle file exists
        """
        return self._bundle_path(item_type, start_id).exists()

    async def _write_bundle(
        self,
        item_type: str,
        start_id: int,
        items_data: list[bytes],
        last_timestamp: Optional[int] = None,
    ) -> None:
        """Write a compressed bundle of items.

        Args:
            item_type: Type of items
            start_id: Starting ID
            items_data: List of raw JSON bytes
            last_timestamp: Timestamp of last item (for mtime)
        """
        bundle_path = self._bundle_path(item_type, start_id)

        # Compress in thread pool to avoid blocking event loop
        data_to_compress = b"\n".join(items_data)
        compressed_data = await asyncio.to_thread(
            lzma.compress,
            data_to_compress,
            preset=config.storage.compression_preset,
        )

        # Write atomically (write to temp, then rename) - use thread pool for I/O
        temp_path = bundle_path.with_suffix(".tmp")
        await asyncio.to_thread(temp_path.write_bytes, compressed_data)
        await asyncio.to_thread(temp_path.rename, bundle_path)

        # Set file mtime to last item's timestamp
        if last_timestamp:
            await asyncio.to_thread(
                os.utime,
                bundle_path,
                (last_timestamp, last_timestamp),
            )

        self.stats.bundles_created += 1
        logger.debug(
            f"Created bundle {bundle_path.name} "
            f"({len(compressed_data):,} bytes compressed)"
        )

    async def download_item_range(
        self,
        start_id: int,
        end_id: int,
        item_type: str = "item",
        client: Optional[HackerNewsClient] = None,
    ) -> None:
        """Download a range of items with bundling.

        Args:
            start_id: First item ID
            end_id: Last item ID (inclusive)
            item_type: Type directory name
            client: Optional existing client to reuse (creates new if None)
        """
        # Reuse provided client or create new one
        should_close_client = client is None
        if client is None:
            client = HackerNewsClient()
            await client.__aenter__()

        try:
            # Process in bundles
            for bundle_start in range(start_id, end_id + 1, self.bundle_size):
                bundle_end = min(bundle_start + self.bundle_size - 1, end_id)

                # Skip if bundle already exists
                if self._bundle_exists(item_type, bundle_start):
                    logger.debug(
                        f"Skipping existing bundle {bundle_start}-{bundle_end}"
                    )
                    continue

                # Fetch items in this bundle
                item_ids = list(range(bundle_start, bundle_end + 1))
                logger.info(f"Fetching items {bundle_start}-{bundle_end}...")

                items_data = await client.get_raw_items_batch(item_ids)

                # Track statistics
                self.stats.total_items += len(items_data)
                non_null = [d for d in items_data if d != b"null"]
                self.stats.successful += len(non_null)
                self.stats.null_responses += len(items_data) - len(non_null)

                # Extract last timestamp for mtime
                last_timestamp = None
                for data in reversed(items_data):
                    if data != b"null":
                        try:
                            item_dict = json.loads(data)
                            last_timestamp = item_dict.get("time")
                            break
                        except (json.JSONDecodeError, KeyError):
                            pass

                # Write bundle
                await self._write_bundle(
                    item_type,
                    bundle_start,
                    items_data,
                    last_timestamp,
                )

                # Log progress (every 10 bundles, plus first bundle)
                if self.stats.bundles_created % 10 == 0 or self.stats.bundles_created == 1:
                    rate = self.stats.items_per_second
                    logger.info(
                        f"Progress: {self.stats.bundles_created} bundles, "
                        f"{self.stats.successful:,} items, "
                        f"{rate:.1f} items/sec"
                    )

        finally:
            # Clean up client if we created it
            if should_close_client and client:
                await client.__aexit__(None, None, None)

    async def download_all_items(self) -> DownloadStats:
        """Download all HackerNews items.

        Returns:
            Download statistics
        """
        self.stats.start_time = time.time()

        # Reuse single client for both operations
        async with HackerNewsClient() as client:
            # Get highest item ID
            highest_id = await client.get_highest_item_id()
            logger.info(f"Starting download of items 0-{highest_id:,}")

            # Download all items using the same client
            await self.download_item_range(0, highest_id, client=client)

        self.stats.end_time = time.time()
        logger.info(f"Download complete: {self.stats}")

        return self.stats

    async def download_users_from_file(self, users_file: Path) -> DownloadStats:
        """Download user profiles from a file containing usernames.

        Args:
            users_file: Path to file with one username per line

        Returns:
            Download statistics
        """
        self.stats.start_time = time.time()

        # Read and validate usernames
        content = await asyncio.to_thread(users_file.read_text)
        usernames = [u.strip() for u in content.split("\n") if u.strip()]

        if not usernames:
            logger.warning(f"No usernames found in {users_file}")
            return self.stats

        logger.info(f"Loaded {len(usernames)} usernames from {users_file}")

        async with HackerNewsClient() as client:
            # Process in batches
            batch_size = config.concurrency.max_concurrent_requests

            for i in range(0, len(usernames), batch_size):
                batch = usernames[i:i + batch_size]
                logger.info(f"Fetching users {i}-{i + len(batch)}...")

                # Fetch users concurrently
                tasks = [client.get_user(username) for username in batch]
                users = await asyncio.gather(*tasks, return_exceptions=True)

                # Write individual user files
                for username, user in zip(batch, users):
                    if isinstance(user, Exception):
                        logger.error(f"Error fetching user {username}: {user}")
                        self.stats.failed += 1
                        continue

                    if user is None:
                        self.stats.null_responses += 1
                        continue

                    # Write user JSON
                    user_dir = self.output_dir / "user"
                    user_dir.mkdir(parents=True, exist_ok=True)
                    user_file = user_dir / f"{username}.json"

                    json_content = json.dumps(
                        user.to_dict(),
                        indent=2,
                        ensure_ascii=False,
                        default=str,
                    )
                    await asyncio.to_thread(user_file.write_text, json_content)

                    self.stats.successful += 1
                    self.stats.total_items += 1

        self.stats.end_time = time.time()
        logger.info(f"User download complete: {self.stats}")

        return self.stats


async def download_with_multiprocessing(
    start_id: int,
    end_id: int,
    num_workers: Optional[int] = None,
) -> None:
    """Download items using multiprocessing for CPU-bound work distribution.

    This function maintains compatibility with the original multiprocessing
    approach while using modern async/await within each worker.

    Args:
        start_id: First item ID
        end_id: Last item ID
        num_workers: Number of worker processes (default: CPU count)
    """
    import multiprocessing
    from functools import partial

    num_workers = num_workers or config.concurrency.multiprocessing_workers
    items_per_worker = config.concurrency.items_per_worker

    # Split range into chunks for each worker
    total_items = end_id - start_id + 1
    chunk_size = items_per_worker

    chunks = [
        (i, min(i + chunk_size - 1, end_id))
        for i in range(start_id, end_id + 1, chunk_size)
    ]

    logger.info(
        f"Starting multiprocessing download: {len(chunks)} chunks "
        f"across {num_workers or 'auto'} workers"
    )

    def worker(chunk: tuple[int, int]) -> None:
        """Worker function to download a chunk of items."""
        chunk_start, chunk_end = chunk
        logger.info(f"Worker processing items {chunk_start}-{chunk_end}")

        # Run async download in this process
        asyncio.run(
            HNDownloader().download_item_range(chunk_start, chunk_end)
        )

    # Execute with multiprocessing
    with multiprocessing.Pool(processes=num_workers, maxtasksperchild=1) as pool:
        pool.map(worker, chunks)

    logger.info("Multiprocessing download complete")
