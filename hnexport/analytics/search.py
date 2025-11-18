"""Full-text search index for HackerNews data.

Build searchable indexes for fast content retrieval.
"""

import json
import lzma
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from ..logger import logger


@dataclass
class SearchResult:
    """Search result item."""

    item_id: int
    type: str
    title: Optional[str]
    text: Optional[str]
    by: Optional[str]
    score: float  # Relevance score
    url: Optional[str] = None
    time: Optional[int] = None


class SearchIndex:
    """Full-text search index using SQLite FTS5.

    Builds a searchable index of HackerNews content for fast full-text search.

    Example:
        # Build index
        index = SearchIndex(data_dir=Path("hn/item"))
        index.build(output_path=Path("hn_search.db"))

        # Search
        results = index.search("python async")
        for result in results:
            print(f"{result.title} by {result.by}")
    """

    def __init__(self, data_dir: Optional[Path] = None, index_path: Optional[Path] = None):
        """Initialize search index.

        Args:
            data_dir: Directory with bundles (for building)
            index_path: Path to existing index database (for searching)
        """
        self.data_dir = data_dir
        self.index_path = index_path
        self.conn: Optional[sqlite3.Connection] = None

        if index_path and index_path.exists():
            self._connect(index_path)

    def _connect(self, path: Path):
        """Connect to index database."""
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row

    def build(
        self,
        output_path: Path,
        item_types: Optional[List[str]] = None,
        max_bundles: Optional[int] = None,
    ) -> int:
        """Build search index from bundles.

        Args:
            output_path: Output database path
            item_types: Item types to index (default: story, comment)
            max_bundles: Max bundles to process (None = all)

        Returns:
            Number of items indexed
        """
        if not self.data_dir:
            raise ValueError("data_dir required for building index")

        if item_types is None:
            item_types = ["story", "comment"]

        # Create database with FTS5
        conn = sqlite3.connect(output_path)
        cursor = conn.cursor()

        # Create FTS5 virtual table
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS search_index USING fts5(
                item_id UNINDEXED,
                type UNINDEXED,
                title,
                text,
                by UNINDEXED,
                url UNINDEXED,
                time UNINDEXED,
                tokenize = 'porter ascii'
            )
        """)

        # Process bundles
        bundles = sorted(self.data_dir.glob("*.xz"))
        if max_bundles:
            bundles = bundles[:max_bundles]

        count = 0
        batch = []
        batch_size = 1000

        logger.info(f"Building search index from {len(bundles)} bundles...")

        for idx, bundle_path in enumerate(bundles):
            try:
                with lzma.open(bundle_path, "rt") as f:
                    content = f.read()

                for line in content.strip().split("\n"):
                    if not line or line == "null":
                        continue

                    try:
                        item = json.loads(line)

                        # Filter by type
                        if item.get("type") not in item_types:
                            continue

                        # Skip deleted
                        if item.get("deleted") or item.get("dead"):
                            continue

                        batch.append((
                            item.get("id"),
                            item.get("type"),
                            item.get("title", ""),
                            item.get("text", ""),
                            item.get("by"),
                            item.get("url"),
                            item.get("time"),
                        ))

                        if len(batch) >= batch_size:
                            cursor.executemany("""
                                INSERT INTO search_index VALUES (?, ?, ?, ?, ?, ?, ?)
                            """, batch)
                            conn.commit()
                            count += len(batch)
                            batch = []

                    except json.JSONDecodeError:
                        pass

                if (idx + 1) % 50 == 0:
                    logger.info(f"Indexed {count:,} items from {idx + 1}/{len(bundles)} bundles...")

            except Exception as e:
                logger.error(f"Error processing {bundle_path.name}: {e}")

        # Insert remaining
        if batch:
            cursor.executemany("""
                INSERT INTO search_index VALUES (?, ?, ?, ?, ?, ?, ?)
            """, batch)
            conn.commit()
            count += len(batch)

        conn.close()
        logger.info(f"Search index built: {count:,} items indexed")

        # Connect to new index
        self._connect(output_path)
        self.index_path = output_path

        return count

    def search(
        self,
        query: str,
        limit: int = 20,
        item_type: Optional[str] = None,
    ) -> List[SearchResult]:
        """Search the index.

        Args:
            query: Search query
            limit: Maximum results
            item_type: Filter by type (optional)

        Returns:
            List of search results ordered by relevance
        """
        if not self.conn:
            raise RuntimeError("No index loaded. Build or load an index first.")

        cursor = self.conn.cursor()

        # Build query
        sql = """
            SELECT
                item_id, type, title, text, by, url, time,
                rank
            FROM search_index
            WHERE search_index MATCH ?
        """

        params = [query]

        if item_type:
            sql += " AND type = ?"
            params.append(item_type)

        sql += " ORDER BY rank LIMIT ?"
        params.append(limit)

        cursor.execute(sql, params)

        results = []
        for row in cursor.fetchall():
            results.append(SearchResult(
                item_id=row["item_id"],
                type=row["type"],
                title=row["title"] if row["title"] else None,
                text=row["text"] if row["text"] else None,
                by=row["by"],
                score=row["rank"],
                url=row["url"],
                time=row["time"],
            ))

        return results

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None
