"""Command-line interface for HNexport.

Modern CLI with async support and better argument parsing.
"""

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Optional

from .config import config
from .downloader import HNDownloader, download_with_multiprocessing
from .logger import logger, setup_logger


def setup_args() -> argparse.ArgumentParser:
    """Set up command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="HNexport - High-performance async HackerNews data export tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download all items
  hnexport --items

  # Download users from file
  hnexport --users usernames.txt

  # Download with custom output directory
  hnexport --items --output /data/hn

  # Download with custom concurrency
  hnexport --items --concurrent 100

  # Use multiprocessing for large downloads
  hnexport --items --multiprocess --workers 8

Environment Variables:
  HNEXPORT_MAX_CONCURRENT - Max concurrent requests (default: 50)
  HNEXPORT_WORKERS - Number of worker processes (default: auto)
  HNEXPORT_OUTPUT_DIR - Output directory (default: ./hn)
  HNEXPORT_LOG_LEVEL - Logging level (default: INFO)
  HNEXPORT_LOG_FILE - Enable file logging (default: false)
        """,
    )

    # Main actions
    action_group = parser.add_mutually_exclusive_group(required=True)
    action_group.add_argument(
        "-i", "--items",
        action="store_true",
        help="Download all HackerNews items",
    )
    action_group.add_argument(
        "-u", "--users",
        type=Path,
        metavar="FILE",
        help="Download user profiles from file (one username per line)",
    )

    # Configuration options
    parser.add_argument(
        "-o", "--output",
        type=Path,
        metavar="DIR",
        help=f"Output directory (default: {config.storage.output_dir})",
    )
    parser.add_argument(
        "-c", "--concurrent",
        type=int,
        metavar="N",
        help=f"Max concurrent requests (default: {config.concurrency.max_concurrent_requests})",
    )
    parser.add_argument(
        "--bundle-size",
        type=int,
        metavar="N",
        default=config.storage.bundle_size,
        help=f"Items per bundle (default: {config.storage.bundle_size})",
    )

    # Multiprocessing options
    parser.add_argument(
        "-m", "--multiprocess",
        action="store_true",
        help="Use multiprocessing for faster downloads",
    )
    parser.add_argument(
        "-w", "--workers",
        type=int,
        metavar="N",
        help="Number of worker processes (default: CPU count)",
    )

    # Logging options
    parser.add_argument(
        "-l", "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default=config.logging.level,
        help=f"Logging level (default: {config.logging.level})",
    )
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Suppress all output except errors",
    )

    # Version
    parser.add_argument(
        "-v", "--version",
        action="version",
        version="HNexport 2.0.0",
    )

    return parser


async def async_main(args: argparse.Namespace) -> int:
    """Async main function.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0 = success, 1 = error)
    """
    try:
        # Configure logging
        if args.quiet:
            setup_logger(level="ERROR")
        else:
            setup_logger(level=args.log_level)

        # Update config from args
        if args.output:
            config.storage.output_dir = args.output
        if args.concurrent:
            config.concurrency.max_concurrent_requests = args.concurrent
        if args.workers:
            config.concurrency.multiprocessing_workers = args.workers

        logger.info(f"HNexport 2.0.0 starting...")
        logger.debug(f"Configuration: {config}")

        # Initialize downloader
        downloader = HNDownloader(
            output_dir=config.storage.output_dir,
            bundle_size=args.bundle_size,
        )

        # Execute requested action
        if args.items:
            logger.info("Starting item download...")

            if args.multiprocess:
                # Use multiprocessing approach
                # First get the highest ID
                from .client import HackerNewsClient

                async with HackerNewsClient() as client:
                    highest_id = await client.get_highest_item_id()

                # Then use multiprocessing
                await download_with_multiprocessing(
                    0,
                    highest_id,
                    num_workers=args.workers,
                )

                logger.info("Multiprocessing download complete!")
            else:
                # Direct async approach
                stats = await downloader.download_all_items()
                logger.info(
                    f"Download complete!\n"
                    f"  Total items: {stats.total_items:,}\n"
                    f"  Successful: {stats.successful:,}\n"
                    f"  Null/deleted: {stats.null_responses:,}\n"
                    f"  Bundles: {stats.bundles_created:,}\n"
                    f"  Duration: {stats.duration:.1f}s\n"
                    f"  Rate: {stats.items_per_second:.1f} items/sec"
                )

        elif args.users:
            if not args.users.exists():
                logger.error(f"Users file not found: {args.users}")
                return 1

            logger.info(f"Starting user download from {args.users}...")
            stats = await downloader.download_users_from_file(args.users)

            logger.info(
                f"User download complete!\n"
                f"  Total users: {stats.total_items:,}\n"
                f"  Successful: {stats.successful:,}\n"
                f"  Failed: {stats.failed:,}\n"
                f"  Duration: {stats.duration:.1f}s"
            )

        return 0

    except KeyboardInterrupt:
        logger.warning("\nInterrupted by user")
        return 130

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        return 1


def main() -> None:
    """Main entry point for CLI."""
    parser = setup_args()
    args = parser.parse_args()

    # Run async main
    exit_code = asyncio.run(async_main(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
