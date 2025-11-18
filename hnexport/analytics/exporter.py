"""Multi-format data exporter for HackerNews data.

Export downloaded bundles to various formats for analysis.
"""

import csv
import json
import lzma
import sqlite3
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterator, List, Optional

from ..logger import logger


class ExportFormat(Enum):
    """Supported export formats."""

    CSV = "csv"
    JSONL = "jsonl"  # JSON Lines
    SQLITE = "sqlite"
    TSV = "tsv"


@dataclass
class ExportConfig:
    """Configuration for data export."""

    format: ExportFormat
    output_path: Path
    include_deleted: bool = False
    item_types: Optional[List[str]] = None  # Filter by type
    batch_size: int = 1000  # For database inserts


class DataExporter:
    """Export HackerNews data to various formats.

    Supports exporting to CSV, JSON Lines, SQLite, and TSV formats
    with flexible filtering and configuration.

    Example:
        exporter = DataExporter(data_dir=Path("hn/item"))

        # Export to CSV
        exporter.export(ExportConfig(
            format=ExportFormat.CSV,
            output_path=Path("hn_data.csv"),
            item_types=["story", "comment"]
        ))

        # Export to SQLite
        exporter.export_to_sqlite(
            output_path=Path("hn.db"),
            create_indexes=True
        )
    """

    def __init__(self, data_dir: Path):
        """Initialize the exporter.

        Args:
            data_dir: Directory containing .xz bundle files
        """
        self.data_dir = data_dir
        logger.info(f"Initialized DataExporter for {data_dir}")

    def _iter_items(
        self,
        include_deleted: bool = False,
        item_types: Optional[List[str]] = None,
    ) -> Iterator[dict]:
        """Iterate over all items in bundles.

        Args:
            include_deleted: Include deleted/dead items
            item_types: Filter by item types (None = all)

        Yields:
            Item dictionaries
        """
        bundles = sorted(self.data_dir.glob("*.xz"))
        logger.info(f"Processing {len(bundles)} bundles...")

        for idx, bundle_path in enumerate(bundles):
            try:
                with lzma.open(bundle_path, "rt") as f:
                    content = f.read()

                for line in content.strip().split("\n"):
                    if not line or line == "null":
                        continue

                    try:
                        item = json.loads(line)

                        # Filter deleted
                        if not include_deleted and (item.get("deleted") or item.get("dead")):
                            continue

                        # Filter by type
                        if item_types and item.get("type") not in item_types:
                            continue

                        yield item

                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON in {bundle_path.name}")

                if (idx + 1) % 100 == 0:
                    logger.info(f"Processed {idx + 1}/{len(bundles)} bundles...")

            except Exception as e:
                logger.error(f"Error processing {bundle_path.name}: {e}")

    def export_to_csv(
        self,
        output_path: Path,
        include_deleted: bool = False,
        item_types: Optional[List[str]] = None,
    ) -> int:
        """Export to CSV format.

        Args:
            output_path: Output CSV file path
            include_deleted: Include deleted items
            item_types: Filter by types

        Returns:
            Number of items exported
        """
        fieldnames = [
            "id",
            "type",
            "by",
            "time",
            "text",
            "dead",
            "parent",
            "poll",
            "url",
            "score",
            "title",
            "descendants",
        ]

        count = 0

        with output_path.open("w", newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(
                csvfile,
                fieldnames=fieldnames,
                extrasaction="ignore",
            )
            writer.writeheader()

            for item in self._iter_items(include_deleted, item_types):
                # Clean text fields (remove newlines for CSV)
                if "text" in item:
                    item["text"] = item["text"].replace("\n", " ").replace("\r", "")
                if "title" in item:
                    item["title"] = item["title"].replace("\n", " ").replace("\r", "")

                writer.writerow(item)
                count += 1

                if count % 10000 == 0:
                    logger.info(f"Exported {count:,} items to CSV...")

        logger.info(f"Exported {count:,} items to {output_path}")
        return count

    def export_to_jsonl(
        self,
        output_path: Path,
        include_deleted: bool = False,
        item_types: Optional[List[str]] = None,
    ) -> int:
        """Export to JSON Lines format.

        Args:
            output_path: Output JSONL file path
            include_deleted: Include deleted items
            item_types: Filter by types

        Returns:
            Number of items exported
        """
        count = 0

        with output_path.open("w", encoding="utf-8") as f:
            for item in self._iter_items(include_deleted, item_types):
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
                count += 1

                if count % 10000 == 0:
                    logger.info(f"Exported {count:,} items to JSONL...")

        logger.info(f"Exported {count:,} items to {output_path}")
        return count

    def export_to_sqlite(
        self,
        output_path: Path,
        include_deleted: bool = False,
        item_types: Optional[List[str]] = None,
        create_indexes: bool = True,
        batch_size: int = 1000,
    ) -> int:
        """Export to SQLite database.

        Args:
            output_path: Output .db file path
            include_deleted: Include deleted items
            item_types: Filter by types
            create_indexes: Create indexes for common queries
            batch_size: Batch size for inserts

        Returns:
            Number of items exported
        """
        # Create database
        conn = sqlite3.connect(output_path)
        cursor = conn.cursor()

        # Create table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY,
                type TEXT NOT NULL,
                by TEXT,
                time INTEGER,
                text TEXT,
                dead INTEGER,
                deleted INTEGER,
                parent INTEGER,
                poll INTEGER,
                url TEXT,
                score INTEGER,
                title TEXT,
                descendants INTEGER,
                kids TEXT  -- JSON array
            )
        """)

        # Batch insert
        count = 0
        batch = []

        for item in self._iter_items(include_deleted, item_types):
            # Convert kids array to JSON string
            kids = item.get("kids")
            if kids:
                kids = json.dumps(kids)

            batch.append((
                item.get("id"),
                item.get("type"),
                item.get("by"),
                item.get("time"),
                item.get("text"),
                1 if item.get("dead") else 0,
                1 if item.get("deleted") else 0,
                item.get("parent"),
                item.get("poll"),
                item.get("url"),
                item.get("score"),
                item.get("title"),
                item.get("descendants"),
                kids,
            ))

            if len(batch) >= batch_size:
                cursor.executemany("""
                    INSERT OR REPLACE INTO items VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                """, batch)
                conn.commit()
                count += len(batch)
                batch = []

                if count % 10000 == 0:
                    logger.info(f"Exported {count:,} items to SQLite...")

        # Insert remaining
        if batch:
            cursor.executemany("""
                INSERT OR REPLACE INTO items VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
            """, batch)
            conn.commit()
            count += len(batch)

        # Create indexes
        if create_indexes:
            logger.info("Creating indexes...")

            cursor.execute("CREATE INDEX IF NOT EXISTS idx_type ON items(type)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_by ON items(by)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_time ON items(time)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_parent ON items(parent)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_score ON items(score)")

            conn.commit()

        conn.close()
        logger.info(f"Exported {count:,} items to {output_path}")
        return count

    def export(self, config: ExportConfig) -> int:
        """Export data according to configuration.

        Args:
            config: Export configuration

        Returns:
            Number of items exported
        """
        if config.format == ExportFormat.CSV:
            return self.export_to_csv(
                config.output_path,
                config.include_deleted,
                config.item_types,
            )
        elif config.format == ExportFormat.JSONL:
            return self.export_to_jsonl(
                config.output_path,
                config.include_deleted,
                config.item_types,
            )
        elif config.format == ExportFormat.SQLITE:
            return self.export_to_sqlite(
                config.output_path,
                config.include_deleted,
                config.item_types,
            )
        elif config.format == ExportFormat.TSV:
            # TSV is similar to CSV but with tab delimiter
            return self._export_to_tsv(
                config.output_path,
                config.include_deleted,
                config.item_types,
            )
        else:
            raise ValueError(f"Unsupported format: {config.format}")

    def _export_to_tsv(
        self,
        output_path: Path,
        include_deleted: bool,
        item_types: Optional[List[str]],
    ) -> int:
        """Export to TSV format."""
        # Similar to CSV but with tab delimiter
        count = self.export_to_csv(
            output_path.with_suffix(".csv"),  # Temp CSV
            include_deleted,
            item_types,
        )

        # Convert to TSV
        with open(output_path.with_suffix(".csv")) as csv_file:
            with open(output_path, "w") as tsv_file:
                for line in csv_file:
                    tsv_file.write(line.replace(",", "\t"))

        # Remove temp CSV
        output_path.with_suffix(".csv").unlink()
        return count
