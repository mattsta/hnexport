"""Trend analysis for HackerNews data."""

import json
import lzma
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

from ..logger import logger


# Common English stop words to filter out
STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "he",
    "in", "is", "it", "its", "of", "on", "that", "the", "to", "was", "will",
    "with", "this", "but", "they", "have", "had", "what", "when", "where", "who",
    "which", "why", "how", "all", "each", "every", "both", "few", "more", "most",
    "other", "some", "such", "no", "nor", "not", "only", "own", "same", "so",
    "than", "too", "very", "can", "just", "should", "now", "i", "you", "we",
}


@dataclass
class TrendReport:
    """Trend analysis report."""

    trending_keywords: List[Tuple[str, int]] = field(default_factory=list)
    trending_domains: List[Tuple[str, int]] = field(default_factory=list)
    activity_by_hour: Dict[int, int] = field(default_factory=dict)
    activity_by_day: Dict[str, int] = field(default_factory=dict)
    growth_metrics: Dict[str, float] = field(default_factory=dict)
    time_window_days: int = 0
    total_items_analyzed: int = 0
    date_range: Tuple[Optional[datetime], Optional[datetime]] = (None, None)

    def to_dict(self) -> Dict:
        """Convert report to dictionary."""
        return {
            "trending_keywords": self.trending_keywords,
            "trending_domains": self.trending_domains,
            "activity_by_hour": self.activity_by_hour,
            "activity_by_day": self.activity_by_day,
            "growth_metrics": self.growth_metrics,
            "time_window_days": self.time_window_days,
            "total_items_analyzed": self.total_items_analyzed,
            "date_range": [
                self.date_range[0].isoformat() if self.date_range[0] else None,
                self.date_range[1].isoformat() if self.date_range[1] else None,
            ],
        }


class TrendAnalyzer:
    """Analyze trends in HackerNews data.

    Identifies trending topics, activity patterns, and growth metrics.
    """

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.item_dir = data_dir / "item" if (data_dir / "item").exists() else data_dir

    def analyze_trends(
        self,
        time_window_days: int = 30,
        top_n: int = 20,
        min_keyword_length: int = 3,
        progress_callback: Optional[callable] = None,
    ) -> TrendReport:
        """Analyze trends over specified time window.

        Args:
            time_window_days: Number of days to analyze (from most recent data)
            top_n: Number of top items to return for each category
            min_keyword_length: Minimum length for keywords to consider
            progress_callback: Optional callback(current, total) for progress

        Returns:
            TrendReport with trending keywords, domains, and activity patterns
        """
        logger.info(f"Analyzing trends for last {time_window_days} days")

        # Calculate cutoff timestamp
        now = datetime.now()
        cutoff_time = (now - timedelta(days=time_window_days)).timestamp()

        # Counters for analysis
        keyword_counter = Counter()
        domain_counter = Counter()
        hour_counter = Counter()
        day_counter = Counter()
        items_by_day: Dict[str, int] = defaultdict(int)

        total_items = 0
        earliest_time = None
        latest_time = None

        # Get all bundles
        bundles = sorted(self.item_dir.glob("*.xz"))
        total_bundles = len(bundles)

        logger.info(f"Processing {total_bundles:,} bundles")

        for idx, bundle_path in enumerate(bundles):
            if progress_callback and idx % 100 == 0:
                progress_callback(idx, total_bundles)

            try:
                with lzma.open(bundle_path, "rt", encoding="utf-8") as f:
                    for line in f:
                        if not line.strip():
                            continue

                        try:
                            item = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        # Skip items outside time window
                        item_time = item.get("time")
                        if not item_time or item_time < cutoff_time:
                            continue

                        total_items += 1

                        # Track date range
                        item_dt = datetime.fromtimestamp(item_time)
                        if earliest_time is None or item_dt < earliest_time:
                            earliest_time = item_dt
                        if latest_time is None or item_dt > latest_time:
                            latest_time = item_dt

                        # Activity by hour
                        hour_counter[item_dt.hour] += 1

                        # Activity by day of week
                        day_name = item_dt.strftime("%A")
                        day_counter[day_name] += 1

                        # Items per day (for growth metrics)
                        day_key = item_dt.strftime("%Y-%m-%d")
                        items_by_day[day_key] += 1

                        # Extract keywords from title
                        if item.get("title"):
                            keywords = self._extract_keywords(
                                item["title"], min_keyword_length
                            )
                            keyword_counter.update(keywords)

                        # Extract keywords from text (comments)
                        if item.get("text"):
                            keywords = self._extract_keywords(
                                item["text"], min_keyword_length, max_words=50
                            )
                            keyword_counter.update(keywords)

                        # Extract domain from URL
                        if item.get("url"):
                            domain = self._extract_domain(item["url"])
                            if domain:
                                domain_counter[domain] += 1

            except Exception as e:
                logger.warning(f"Error processing bundle {bundle_path.name}: {e}")
                continue

        if progress_callback:
            progress_callback(total_bundles, total_bundles)

        # Build report
        report = TrendReport(
            trending_keywords=keyword_counter.most_common(top_n),
            trending_domains=domain_counter.most_common(top_n),
            activity_by_hour=dict(hour_counter),
            activity_by_day=dict(day_counter),
            time_window_days=time_window_days,
            total_items_analyzed=total_items,
            date_range=(earliest_time, latest_time),
        )

        # Calculate growth metrics
        if len(items_by_day) > 1:
            report.growth_metrics = self._calculate_growth_metrics(items_by_day)

        logger.info(
            f"Trend analysis complete: {total_items:,} items, "
            f"{len(keyword_counter):,} unique keywords, "
            f"{len(domain_counter):,} unique domains"
        )

        return report

    def _extract_keywords(
        self, text: str, min_length: int = 3, max_words: int = None
    ) -> List[str]:
        """Extract keywords from text.

        Args:
            text: Text to extract keywords from
            min_length: Minimum keyword length
            max_words: Maximum number of words to process (for long text)

        Returns:
            List of keywords
        """
        # Convert to lowercase and extract words
        words = re.findall(r"\b[a-z]+\b", text.lower())

        # Limit processing for long text
        if max_words and len(words) > max_words:
            words = words[:max_words]

        # Filter: remove stop words and short words
        keywords = [
            word
            for word in words
            if len(word) >= min_length and word not in STOP_WORDS
        ]

        return keywords

    def _extract_domain(self, url: str) -> Optional[str]:
        """Extract domain from URL.

        Args:
            url: URL to parse

        Returns:
            Domain name or None
        """
        try:
            parsed = urlparse(url)
            domain = parsed.netloc

            # Remove www. prefix
            if domain.startswith("www."):
                domain = domain[4:]

            return domain if domain else None
        except Exception:
            return None

    def _calculate_growth_metrics(
        self, items_by_day: Dict[str, int]
    ) -> Dict[str, float]:
        """Calculate growth metrics from daily item counts.

        Args:
            items_by_day: Dictionary mapping date string to item count

        Returns:
            Dictionary with growth metrics
        """
        sorted_days = sorted(items_by_day.items())

        if len(sorted_days) < 2:
            return {}

        # Get first and last week averages
        first_week_days = sorted_days[:7]
        last_week_days = sorted_days[-7:]

        first_week_avg = sum(count for _, count in first_week_days) / len(
            first_week_days
        )
        last_week_avg = sum(count for _, count in last_week_days) / len(last_week_days)

        # Calculate overall average
        total_items = sum(count for _, count in sorted_days)
        avg_per_day = total_items / len(sorted_days)

        # Calculate growth rate
        growth_rate = 0.0
        if first_week_avg > 0:
            growth_rate = ((last_week_avg - first_week_avg) / first_week_avg) * 100

        # Find peak day
        peak_day, peak_count = max(sorted_days, key=lambda x: x[1])

        return {
            "average_items_per_day": round(avg_per_day, 2),
            "first_week_average": round(first_week_avg, 2),
            "last_week_average": round(last_week_avg, 2),
            "growth_rate_percent": round(growth_rate, 2),
            "peak_day": peak_day,
            "peak_day_count": peak_count,
        }

    def get_trending_keywords_over_time(
        self,
        keyword: str,
        days: int = 30,
        bucket_hours: int = 24,
    ) -> List[Tuple[datetime, int]]:
        """Track how often a specific keyword appears over time.

        Args:
            keyword: Keyword to track
            days: Number of days to analyze
            bucket_hours: Hours per time bucket (default 24 = daily)

        Returns:
            List of (timestamp, count) tuples
        """
        logger.info(f"Tracking keyword '{keyword}' over {days} days")

        cutoff_time = (datetime.now() - timedelta(days=days)).timestamp()
        keyword_lower = keyword.lower()

        # Time buckets
        time_buckets: Dict[datetime, int] = defaultdict(int)

        bundles = sorted(self.item_dir.glob("*.xz"))

        for bundle_path in bundles:
            try:
                with lzma.open(bundle_path, "rt", encoding="utf-8") as f:
                    for line in f:
                        if not line.strip():
                            continue

                        try:
                            item = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        item_time = item.get("time")
                        if not item_time or item_time < cutoff_time:
                            continue

                        # Check if keyword appears
                        text = ""
                        if item.get("title"):
                            text += item["title"].lower() + " "
                        if item.get("text"):
                            text += item["text"].lower()

                        if keyword_lower in text:
                            # Bucket by time
                            item_dt = datetime.fromtimestamp(item_time)
                            bucket_dt = item_dt.replace(
                                hour=0, minute=0, second=0, microsecond=0
                            )

                            # Adjust bucket size if needed
                            if bucket_hours != 24:
                                bucket_hour = (item_dt.hour // bucket_hours) * bucket_hours
                                bucket_dt = bucket_dt.replace(hour=bucket_hour)

                            time_buckets[bucket_dt] += 1

            except Exception as e:
                logger.warning(f"Error processing bundle {bundle_path.name}: {e}")
                continue

        # Convert to sorted list
        result = sorted(time_buckets.items())

        logger.info(f"Found {len(result)} time buckets with keyword '{keyword}'")
        return result
