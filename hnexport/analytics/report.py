"""Comprehensive analytics report generation."""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from ..logger import logger
from .stats import StatsAnalyzer, StatsReport
from .trends import TrendAnalyzer, TrendReport
from .validator import DataValidator, ValidationReport


@dataclass
class ComprehensiveReport:
    """Complete analytics report combining multiple analyses."""

    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    data_directory: str = ""
    stats: Optional[StatsReport] = None
    trends: Optional[TrendReport] = None
    validation: Optional[ValidationReport] = None
    summary: Dict[str, any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """Convert report to dictionary."""
        report_dict = {
            "generated_at": self.generated_at,
            "data_directory": self.data_directory,
            "summary": self.summary,
        }

        if self.stats:
            report_dict["statistics"] = self.stats.to_dict()

        if self.trends:
            report_dict["trends"] = self.trends.to_dict()

        if self.validation:
            report_dict["validation"] = self.validation.to_dict()

        return report_dict

    def to_json(self, indent: int = 2) -> str:
        """Convert report to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def to_markdown(self) -> str:
        """Convert report to Markdown format."""
        lines = [
            "# HackerNews Analytics Report",
            "",
            f"**Generated:** {self.generated_at}",
            f"**Data Directory:** {self.data_directory}",
            "",
        ]

        # Summary
        if self.summary:
            lines.extend(
                [
                    "## Summary",
                    "",
                ]
            )

            for key, value in self.summary.items():
                lines.append(f"- **{key}:** {value:,}" if isinstance(value, int) else f"- **{key}:** {value}")

            lines.append("")

        # Statistics
        if self.stats:
            lines.extend(
                [
                    "## Statistics",
                    "",
                    f"- **Total Items:** {self.stats.total_items:,}",
                    f"- **Total Bundles:** {self.stats.total_bundles:,}",
                    f"- **Unique Users:** {self.stats.unique_users:,}",
                    "",
                    "### By Type",
                    "",
                ]
            )

            for item_type, count in self.stats.by_type.items():
                lines.append(f"- **{item_type}:** {count:,}")

            lines.append("")

            # Top submitters
            if self.stats.top_submitters:
                lines.extend(["### Top Submitters", ""])
                for user, count in self.stats.top_submitters[:10]:
                    lines.append(f"- **{user}:** {count:,}")
                lines.append("")

            # Top commenters
            if self.stats.top_commenters:
                lines.extend(["### Top Commenters", ""])
                for user, count in self.stats.top_commenters[:10]:
                    lines.append(f"- **{user}:** {count:,}")
                lines.append("")

            # Top domains
            if self.stats.top_domains:
                lines.extend(["### Top Domains", ""])
                for domain, count in self.stats.top_domains[:10]:
                    lines.append(f"- **{domain}:** {count:,}")
                lines.append("")

        # Trends
        if self.trends:
            lines.extend(
                [
                    "## Trends",
                    "",
                    f"**Time Window:** {self.trends.time_window_days} days",
                    f"**Items Analyzed:** {self.trends.total_items_analyzed:,}",
                    "",
                ]
            )

            # Trending keywords
            if self.trends.trending_keywords:
                lines.extend(["### Trending Keywords", ""])
                for keyword, count in self.trends.trending_keywords[:15]:
                    lines.append(f"- **{keyword}:** {count:,}")
                lines.append("")

            # Trending domains
            if self.trends.trending_domains:
                lines.extend(["### Trending Domains", ""])
                for domain, count in self.trends.trending_domains[:10]:
                    lines.append(f"- **{domain}:** {count:,}")
                lines.append("")

            # Activity by hour
            if self.trends.activity_by_hour:
                lines.extend(["### Activity by Hour", ""])
                for hour in range(24):
                    count = self.trends.activity_by_hour.get(hour, 0)
                    if count > 0:
                        bar = "█" * (count // max(self.trends.activity_by_hour.values()) * 40)
                        lines.append(f"- **{hour:02d}:00** {bar} ({count:,})")
                lines.append("")

            # Growth metrics
            if self.trends.growth_metrics:
                lines.extend(["### Growth Metrics", ""])
                for metric, value in self.trends.growth_metrics.items():
                    if isinstance(value, (int, float)):
                        lines.append(f"- **{metric}:** {value:,.2f}")
                    else:
                        lines.append(f"- **{metric}:** {value}")
                lines.append("")

        # Validation
        if self.validation:
            lines.extend(
                [
                    "## Data Validation",
                    "",
                    f"- **Total Bundles:** {self.validation.total_bundles:,}",
                    f"- **Valid Bundles:** {self.validation.valid_bundles:,}",
                    f"- **Corrupt Bundles:** {len(self.validation.corrupt_bundles):,}",
                    f"- **Total Items:** {self.validation.total_items:,}",
                    f"- **Valid Items:** {self.validation.valid_items:,}",
                    f"- **Duplicate IDs:** {len(self.validation.duplicate_ids):,}",
                    f"- **Missing IDs:** {len(self.validation.missing_ids):,}",
                    "",
                ]
            )

            if self.validation.schema_errors:
                lines.extend(["### Schema Errors", ""])
                for error_type, count in sorted(self.validation.schema_errors.items()):
                    lines.append(f"- **{error_type}:** {count:,}")
                lines.append("")

        return "\n".join(lines)

    def to_html(self) -> str:
        """Convert report to HTML format."""
        # Simple HTML conversion (could be enhanced with templates)
        markdown = self.to_markdown()

        # Basic markdown to HTML conversion
        html = markdown.replace("# ", "<h1>").replace("</h1>", "")
        html = html.replace("## ", "<h2>").replace("</h2>", "")
        html = html.replace("### ", "<h3>").replace("</h3>", "")
        html = html.replace("- **", "<li><strong>").replace("**", "</strong>")

        return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>HackerNews Analytics Report</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 40px; }}
        h1 {{ color: #ff6600; }}
        h2 {{ margin-top: 30px; border-bottom: 1px solid #ccc; padding-bottom: 10px; }}
        h3 {{ color: #666; }}
        li {{ margin: 5px 0; }}
    </style>
</head>
<body>
{html}
</body>
</html>
"""


class ReportGenerator:
    """Generate comprehensive analytics reports.

    Combines multiple analytics features (statistics, trends, validation)
    into unified reports in various formats.

    Example:
        generator = ReportGenerator(data_dir=Path("hn/item"))
        report = generator.generate_full_report()
        Path("report.md").write_text(report.to_markdown())
    """

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir

    def generate_full_report(
        self,
        include_stats: bool = True,
        include_trends: bool = True,
        include_validation: bool = True,
        max_bundles: Optional[int] = None,
        trend_window_days: int = 30,
        progress_callback: Optional[callable] = None,
    ) -> ComprehensiveReport:
        """Generate comprehensive report with all analytics.

        Args:
            include_stats: Include statistics analysis
            include_trends: Include trend analysis
            include_validation: Include data validation
            max_bundles: Maximum bundles to analyze (None = all)
            trend_window_days: Days to analyze for trends
            progress_callback: Optional progress callback

        Returns:
            ComprehensiveReport with all requested analyses
        """
        logger.info("Generating comprehensive analytics report")

        report = ComprehensiveReport(
            data_directory=str(self.data_dir),
        )

        # Statistics
        if include_stats:
            logger.info("Running statistics analysis")
            stats_analyzer = StatsAnalyzer(self.data_dir)
            report.stats = stats_analyzer.analyze(
                max_bundles=max_bundles,
                progress_callback=progress_callback,
            )

        # Trends
        if include_trends:
            logger.info("Running trend analysis")
            trend_analyzer = TrendAnalyzer(self.data_dir)
            report.trends = trend_analyzer.analyze_trends(
                time_window_days=trend_window_days,
                progress_callback=progress_callback,
            )

        # Validation
        if include_validation:
            logger.info("Running data validation")
            validator = DataValidator(self.data_dir)
            report.validation = validator.validate(
                check_gaps=False,  # Expensive for large datasets
                progress_callback=progress_callback,
            )

        # Generate summary
        report.summary = self._generate_summary(report)

        logger.info("Report generation complete")
        return report

    def generate_quick_report(self, sample_bundles: int = 100) -> ComprehensiveReport:
        """Generate quick report from sample data.

        Args:
            sample_bundles: Number of bundles to sample

        Returns:
            ComprehensiveReport from sample data
        """
        logger.info(f"Generating quick report (sampling {sample_bundles} bundles)")

        return self.generate_full_report(
            include_stats=True,
            include_trends=False,
            include_validation=False,
            max_bundles=sample_bundles,
        )

    def _generate_summary(self, report: ComprehensiveReport) -> Dict:
        """Generate summary from report data.

        Args:
            report: Report to summarize

        Returns:
            Dictionary of summary statistics
        """
        summary = {}

        if report.stats:
            summary["Total Items"] = report.stats.total_items
            summary["Total Bundles"] = report.stats.total_bundles
            summary["Unique Users"] = report.stats.unique_users

            if report.stats.time_range[0] and report.stats.time_range[1]:
                summary["Date Range"] = (
                    f"{report.stats.time_range[0].strftime('%Y-%m-%d')} to "
                    f"{report.stats.time_range[1].strftime('%Y-%m-%d')}"
                )

        if report.trends:
            summary["Trend Window (days)"] = report.trends.time_window_days
            summary["Items in Trend Window"] = report.trends.total_items_analyzed

        if report.validation:
            summary["Valid Bundles"] = report.validation.valid_bundles
            summary["Data Quality"] = (
                f"{(report.validation.valid_bundles / max(report.validation.total_bundles, 1)) * 100:.1f}%"
            )

        return summary

    def export_report(
        self,
        report: ComprehensiveReport,
        output_path: Path,
        format: str = "json",
    ) -> None:
        """Export report to file.

        Args:
            report: Report to export
            output_path: Output file path
            format: Export format (json, markdown, html)
        """
        logger.info(f"Exporting report to {output_path} ({format} format)")

        if format == "json":
            content = report.to_json()
        elif format == "markdown" or format == "md":
            content = report.to_markdown()
        elif format == "html":
            content = report.to_html()
        else:
            raise ValueError(f"Unsupported format: {format}. Use: json, markdown, html")

        output_path.write_text(content, encoding="utf-8")
        logger.info(f"Report exported: {output_path}")


# CLI helper
def main():
    """CLI entry point for report generation."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m hnexport.analytics.report <data_dir> [output_file] [format]")
        print("Formats: json, markdown, html")
        sys.exit(1)

    data_dir = Path(sys.argv[1])
    output_file = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("hn_report.json")
    format = sys.argv[3] if len(sys.argv) > 3 else "json"

    # Progress callback
    def progress(current, total):
        pct = (current / total * 100) if total > 0 else 0
        print(f"\rProgress: {current:,}/{total:,} ({pct:.1f}%)", end="", flush=True)

    print("Generating comprehensive analytics report...")
    print()

    generator = ReportGenerator(data_dir)
    report = generator.generate_full_report(
        max_bundles=1000,  # Sample for demo
        progress_callback=progress,
    )

    print("\n")
    print(report.to_markdown()[:500])  # Preview
    print("\n...")

    generator.export_report(report, output_file, format=format)
    print(f"\nFull report saved to: {output_file}")


if __name__ == "__main__":
    main()
