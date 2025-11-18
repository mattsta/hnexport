"""Statistics analyzer for HackerNews data.

Generates comprehensive statistics from downloaded bundles.
"""

import json
import lzma
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..logger import logger


@dataclass
class StatsReport:
    """Comprehensive statistics report."""

    # Overall stats
    total_items: int = 0
    total_bundles: int = 0

    # By type
    stories: int = 0
    comments: int = 0
    jobs: int = 0
    polls: int = 0
    pollopts: int = 0
    deleted: int = 0

    # User stats
    total_users: int = 0
    top_submitters: List[Tuple[str, int]] = field(default_factory=list)
    top_commenters: List[Tuple[str, int]] = field(default_factory=list)

    # Time stats
    earliest_timestamp: Optional[int] = None
    latest_timestamp: Optional[int] = None
    items_by_year: Dict[int, int] = field(default_factory=dict)

    # Content stats
    total_words: int = 0
    avg_comment_length: float = 0.0
    avg_story_score: float = 0.0

    # Domain stats
    top_domains: List[Tuple[str, int]] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "overall": {
                "total_items": self.total_items,
                "total_bundles": self.total_bundles,
                "total_users": self.total_users,
            },
            "by_type": {
                "stories": self.stories,
                "comments": self.comments,
                "jobs": self.jobs,
                "polls": self.polls,
                "pollopts": self.pollopts,
                "deleted": self.deleted,
            },
            "top_submitters": dict(self.top_submitters[:20]),
            "top_commenters": dict(self.top_commenters[:20]),
            "time_range": {
                "earliest": (
                    datetime.fromtimestamp(self.earliest_timestamp).isoformat()
                    if self.earliest_timestamp
                    else None
                ),
                "latest": (
                    datetime.fromtimestamp(self.latest_timestamp).isoformat()
                    if self.latest_timestamp
                    else None
                ),
            },
            "items_by_year": self.items_by_year,
            "content": {
                "total_words": self.total_words,
                "avg_comment_length": round(self.avg_comment_length, 2),
                "avg_story_score": round(self.avg_story_score, 2),
            },
            "top_domains": dict(self.top_domains[:20]),
        }

    def __str__(self) -> str:
        """Human-readable report."""
        lines = [
            "=" * 60,
            "HackerNews Statistics Report",
            "=" * 60,
            "",
            "OVERALL STATISTICS",
            f"  Total Items:    {self.total_items:,}",
            f"  Total Bundles:  {self.total_bundles:,}",
            f"  Total Users:    {self.total_users:,}",
            "",
            "BY TYPE",
            f"  Stories:        {self.stories:,}",
            f"  Comments:       {self.comments:,}",
            f"  Jobs:           {self.jobs:,}",
            f"  Polls:          {self.polls:,}",
            f"  Poll Options:   {self.pollopts:,}",
            f"  Deleted:        {self.deleted:,}",
            "",
            "TOP SUBMITTERS (Stories/Jobs/Polls)",
        ]

        for user, count in self.top_submitters[:10]:
            lines.append(f"  {user:20s} {count:6,d}")

        lines.extend([
            "",
            "TOP COMMENTERS",
        ])

        for user, count in self.top_commenters[:10]:
            lines.append(f"  {user:20s} {count:6,d}")

        if self.earliest_timestamp and self.latest_timestamp:
            earliest = datetime.fromtimestamp(self.earliest_timestamp)
            latest = datetime.fromtimestamp(self.latest_timestamp)
            lines.extend([
                "",
                "TIME RANGE",
                f"  Earliest: {earliest.strftime('%Y-%m-%d %H:%M:%S')}",
                f"  Latest:   {latest.strftime('%Y-%m-%d %H:%M:%S')}",
                f"  Span:     {(latest - earliest).days:,} days",
            ])

        lines.extend([
            "",
            "CONTENT STATISTICS",
            f"  Total Words:           {self.total_words:,}",
            f"  Avg Comment Length:    {self.avg_comment_length:.0f} chars",
            f"  Avg Story Score:       {self.avg_story_score:.1f}",
            "",
            "TOP DOMAINS",
        ])

        for domain, count in self.top_domains[:10]:
            lines.append(f"  {domain:30s} {count:6,d}")

        lines.extend(["", "=" * 60])

        return "\n".join(lines)


class StatsAnalyzer:
    """Analyze statistics from HackerNews bundles.

    This analyzer processes downloaded bundles and generates comprehensive
    statistics about the content, users, and trends.

    Example:
        analyzer = StatsAnalyzer(data_dir=Path("hn/item"))
        report = analyzer.analyze()
        print(report)
        report.save_json("stats.json")
    """

    def __init__(self, data_dir: Path):
        """Initialize the analyzer.

        Args:
            data_dir: Directory containing .xz bundle files
        """
        self.data_dir = data_dir
        logger.info(f"Initialized StatsAnalyzer for {data_dir}")

    def _parse_bundle(self, bundle_path: Path) -> List[dict]:
        """Parse a bundle file into items.

        Args:
            bundle_path: Path to .xz bundle file

        Returns:
            List of item dictionaries
        """
        try:
            with lzma.open(bundle_path, "rt") as f:
                content = f.read()

            items = []
            for line in content.strip().split("\n"):
                if line and line != "null":
                    try:
                        items.append(json.loads(line))
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON in {bundle_path.name}")

            return items

        except Exception as e:
            logger.error(f"Error parsing {bundle_path.name}: {e}")
            return []

    def _extract_domain(self, url: Optional[str]) -> Optional[str]:
        """Extract domain from URL.

        Args:
            url: Full URL

        Returns:
            Domain name or None
        """
        if not url:
            return None

        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            return parsed.netloc or None
        except Exception:
            return None

    def analyze(
        self,
        max_bundles: Optional[int] = None,
        progress_callback: Optional[callable] = None,
    ) -> StatsReport:
        """Analyze all bundles and generate statistics.

        Args:
            max_bundles: Maximum number of bundles to process (None = all)
            progress_callback: Optional callback(current, total) for progress

        Returns:
            StatsReport with comprehensive statistics
        """
        report = StatsReport()

        # Counters for aggregation
        submitters = Counter()  # username -> count (stories/jobs/polls)
        commenters = Counter()  # username -> count (comments)
        domains = Counter()  # domain -> count
        years = Counter()  # year -> count

        comment_lengths = []
        story_scores = []
        all_users = set()

        # Find all bundles
        bundles = sorted(self.data_dir.glob("*.xz"))

        if max_bundles:
            bundles = bundles[:max_bundles]

        report.total_bundles = len(bundles)
        logger.info(f"Analyzing {len(bundles)} bundles...")

        # Process each bundle
        for idx, bundle_path in enumerate(bundles):
            items = self._parse_bundle(bundle_path)

            for item in items:
                item_type = item.get("type")
                item_by = item.get("by")
                item_time = item.get("time")
                item_deleted = item.get("deleted") or item.get("dead")

                report.total_items += 1

                # Track users
                if item_by:
                    all_users.add(item_by)

                # Track deleted
                if item_deleted:
                    report.deleted += 1
                    continue

                # Track by type
                if item_type == "story":
                    report.stories += 1
                    if item_by:
                        submitters[item_by] += 1

                    # Track score
                    score = item.get("score")
                    if score is not None:
                        story_scores.append(score)

                    # Track domain
                    url = item.get("url")
                    if url:
                        domain = self._extract_domain(url)
                        if domain:
                            domains[domain] += 1

                elif item_type == "comment":
                    report.comments += 1
                    if item_by:
                        commenters[item_by] += 1

                    # Track comment length
                    text = item.get("text", "")
                    comment_lengths.append(len(text))

                    # Count words
                    report.total_words += len(text.split())

                elif item_type == "job":
                    report.jobs += 1
                    if item_by:
                        submitters[item_by] += 1

                elif item_type == "poll":
                    report.polls += 1
                    if item_by:
                        submitters[item_by] += 1

                elif item_type == "pollopt":
                    report.pollopts += 1

                # Track time
                if item_time:
                    if report.earliest_timestamp is None or item_time < report.earliest_timestamp:
                        report.earliest_timestamp = item_time
                    if report.latest_timestamp is None or item_time > report.latest_timestamp:
                        report.latest_timestamp = item_time

                    year = datetime.fromtimestamp(item_time).year
                    years[year] += 1

            # Progress callback
            if progress_callback:
                progress_callback(idx + 1, len(bundles))

            # Log progress
            if (idx + 1) % 100 == 0:
                logger.info(f"Processed {idx + 1}/{len(bundles)} bundles...")

        # Finalize stats
        report.total_users = len(all_users)
        report.top_submitters = submitters.most_common(50)
        report.top_commenters = commenters.most_common(50)
        report.top_domains = domains.most_common(50)
        report.items_by_year = dict(sorted(years.items()))

        if comment_lengths:
            report.avg_comment_length = sum(comment_lengths) / len(comment_lengths)

        if story_scores:
            report.avg_story_score = sum(story_scores) / len(story_scores)

        logger.info("Analysis complete!")
        return report

    def save_report(self, report: StatsReport, output_path: Path, format: str = "json"):
        """Save report to file.

        Args:
            report: StatsReport to save
            output_path: Output file path
            format: Output format ("json" or "txt")
        """
        if format == "json":
            output_path.write_text(
                json.dumps(report.to_dict(), indent=2, ensure_ascii=False)
            )
        else:  # txt
            output_path.write_text(str(report))

        logger.info(f"Report saved to {output_path}")
