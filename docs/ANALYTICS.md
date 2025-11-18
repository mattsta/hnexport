# HNexport Analytics & Extensions

Comprehensive guide to the analytics features and extensions for HNexport.

## Overview

The analytics package provides 12+ powerful features for analyzing, exporting, and processing downloaded HackerNews data.

## Features

### 1. Statistics Dashboard (`stats.py`)

Generate comprehensive statistics from downloaded bundles.

**Features:**
- Overall statistics (total items, bundles, users)
- Breakdown by type (stories, comments, jobs, polls)
- Top submitters and commenters
- Time range analysis
- Content statistics (words, comment length, scores)
- Top domains analysis

**Usage:**
```python
from pathlib import Path
from hnexport.analytics import StatsAnalyzer

# Analyze data
analyzer = StatsAnalyzer(data_dir=Path("hn/item"))
report = analyzer.analyze()

# Print report
print(report)

# Save to JSON
import json
Path("stats.json").write_text(
    json.dumps(report.to_dict(), indent=2)
)
```

**CLI:**
```bash
# Generate stats
python3 -m hnexport.analytics.stats hn/item --output stats.json

# With progress
python3 -m hnexport.analytics.stats hn/item --progress
```

**Output Example:**
```
====================================================================
HackerNews Statistics Report
====================================================================

OVERALL STATISTICS
  Total Items:    45,961,213
  Total Bundles:  459,612
  Total Users:    1,234,567

BY TYPE
  Stories:        12,345,678
  Comments:       32,456,789
  Jobs:           567,890
  Polls:          12,345
  Poll Options:   45,678
  Deleted:        234,567

TOP SUBMITTERS (Stories/Jobs/Polls)
  pg                    12,345
  dang                  10,234
  ...

TOP COMMENTERS
  tptacek               45,678
  ...

TOP DOMAINS
  github.com            123,456
  youtube.com           98,765
  ...
```

---

### 2. Data Exporter (`exporter.py`)

Export data to multiple formats for analysis.

**Supported Formats:**
- CSV (Comma-Separated Values)
- JSONL (JSON Lines)
- SQLite (Indexed database)
- TSV (Tab-Separated Values)

**Usage:**
```python
from pathlib import Path
from hnexport.analytics import DataExporter, ExportFormat, ExportConfig

exporter = DataExporter(data_dir=Path("hn/item"))

# Export to CSV
exporter.export(ExportConfig(
    format=ExportFormat.CSV,
    output_path=Path("hn_data.csv"),
    item_types=["story", "comment"],
    include_deleted=False
))

# Export to SQLite with indexes
count = exporter.export_to_sqlite(
    output_path=Path("hn.db"),
    create_indexes=True
)
print(f"Exported {count:,} items")
```

**SQLite Schema:**
```sql
CREATE TABLE items (
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
);

-- Indexes
CREATE INDEX idx_type ON items(type);
CREATE INDEX idx_by ON items(by);
CREATE INDEX idx_time ON items(time);
CREATE INDEX idx_parent ON items(parent);
CREATE INDEX idx_score ON items(score);
```

**Querying SQLite:**
```bash
sqlite3 hn.db "SELECT title, score FROM items WHERE type='story' ORDER BY score DESC LIMIT 10"
```

---

### 3. Full-Text Search Index (`search.py`)

Build searchable indexes using SQLite FTS5.

**Features:**
- Full-text search with ranking
- Porter stemming
- Fast indexed queries
- Type filtering

**Usage:**
```python
from pathlib import Path
from hnexport.analytics import SearchIndex

# Build index
index = SearchIndex(data_dir=Path("hn/item"))
index.build(
    output_path=Path("hn_search.db"),
    item_types=["story", "comment"]
)

# Search
results = index.search("python async", limit=10)

for result in results:
    print(f"[{result.type}] {result.title or result.text[:50]}")
    print(f"  by {result.by} | score: {result.score}")
    print()
```

**Advanced Queries:**
```python
# Search stories only
results = index.search("machine learning", item_type="story")

# Boolean operators
results = index.search("python AND async")
results = index.search("python OR javascript")
results = index.search("python NOT django")

# Phrase search
results = index.search('"machine learning"')
```

---

### 4. Trend Analyzer (`trends.py`)

Analyze trends and patterns over time.

**Features:**
- Trending keywords
- Trending domains
- Activity patterns by hour/day
- Growth metrics

**Usage:**
```python
from hnexport.analytics import TrendAnalyzer

analyzer = TrendAnalyzer(data_dir=Path("hn/item"))

# Analyze last 30 days
report = analyzer.analyze_trends(
    time_window_days=30,
    top_n=20
)

print(f"Trending Keywords: {report.trending_keywords[:10]}")
print(f"Peak Activity Hour: {max(report.activity_by_hour.items())}")
```

---

### 5. Data Validator (`validator.py`)

Validate data integrity and completeness.

**Features:**
- Corruption detection
- Missing item detection
- Duplicate detection
- Consistency checks

**Usage:**
```python
from hnexport.analytics import DataValidator

validator = DataValidator(data_dir=Path("hn/item"))
report = validator.validate()

print(f"Valid Bundles: {report.valid_bundles}/{report.total_bundles}")
print(f"Corrupt Bundles: {len(report.corrupt_bundles)}")
print(f"Duplicate IDs: {len(report.duplicate_ids)}")

if report.corrupt_bundles:
    print("Corrupt bundles:")
    for bundle in report.corrupt_bundles:
        print(f"  - {bundle}")
```

---

## Complete Examples

### Example 1: Generate Comprehensive Report

```python
#!/usr/bin/env python3
"""Generate comprehensive analytics report."""

import json
from pathlib import Path
from hnexport.analytics import (
    StatsAnalyzer,
    DataValidator,
    TrendAnalyzer,
)

data_dir = Path("hn/item")

# 1. Generate statistics
print("Generating statistics...")
stats_analyzer = StatsAnalyzer(data_dir)
stats_report = stats_analyzer.analyze(max_bundles=100)  # Sample
print(stats_report)

# 2. Validate data
print("\nValidating data...")
validator = DataValidator(data_dir)
validation_report = validator.validate()
print(f"Valid: {validation_report.valid_bundles}/{validation_report.total_bundles}")

# 3. Analyze trends
print("\nAnalyzing trends...")
trend_analyzer = TrendAnalyzer(data_dir)
trend_report = trend_analyzer.analyze_trends(time_window_days=7)

# 4. Save comprehensive report
report = {
    "stats": stats_report.to_dict(),
    "validation": {
        "valid_bundles": validation_report.valid_bundles,
        "total_bundles": validation_report.total_bundles,
        "corrupt": validation_report.corrupt_bundles,
    },
    "trends": {
        "keywords": trend_report.trending_keywords[:20],
        "domains": trend_report.trending_domains[:20],
    }
}

Path("comprehensive_report.json").write_text(
    json.dumps(report, indent=2, ensure_ascii=False)
)

print("\nReport saved to comprehensive_report.json")
```

### Example 2: Build Multi-Format Exports

```python
#!/usr/bin/env python3
"""Export data to multiple formats."""

from pathlib import Path
from hnexport.analytics import DataExporter, ExportFormat, ExportConfig

data_dir = Path("hn/item")
exporter = DataExporter(data_dir)

# Export stories to CSV
print("Exporting stories to CSV...")
exporter.export(ExportConfig(
    format=ExportFormat.CSV,
    output_path=Path("stories.csv"),
    item_types=["story"]
))

# Export comments to JSONL
print("Exporting comments to JSONL...")
exporter.export(ExportConfig(
    format=ExportFormat.JSONL,
    output_path=Path("comments.jsonl"),
    item_types=["comment"]
))

# Export everything to SQLite
print("Exporting all to SQLite...")
count = exporter.export_to_sqlite(
    output_path=Path("hn_complete.db"),
    create_indexes=True
)

print(f"\nExported {count:,} items total")
```

### Example 3: Build Search Portal

```python
#!/usr/bin/env python3
"""Interactive search portal."""

from pathlib import Path
from hnexport.analytics import SearchIndex

# Build index (one-time)
print("Building search index...")
index = SearchIndex(data_dir=Path("hn/item"))
index.build(
    output_path=Path("hn_search.db"),
    item_types=["story", "comment"],
    max_bundles=1000  # For demo
)

# Search loop
print("\nSearch Portal Ready!")
print("Enter queries (or 'quit' to exit)")

while True:
    query = input("\nSearch> ").strip()

    if query.lower() in ("quit", "exit", "q"):
        break

    if not query:
        continue

    results = index.search(query, limit=5)

    print(f"\nFound {len(results)} results:")
    for i, result in enumerate(results, 1):
        print(f"\n{i}. [{result.type}] by {result.by}")
        if result.title:
            print(f"   {result.title}")
        if result.text:
            print(f"   {result.text[:100]}...")
        if result.url:
            print(f"   {result.url}")

index.close()
```

---

## Performance Considerations

### Statistics Analysis
- **Memory**: ~200 MB for full analysis
- **Time**: ~5-10 minutes for 45M items
- **Optimization**: Use `max_bundles` parameter for sampling

### Data Export
- **CSV**: ~10-15 GB uncompressed for 45M items
- **SQLite**: ~8-12 GB with indexes
- **Time**: ~15-30 minutes for full export

### Search Index
- **Build Time**: ~20-40 minutes for 45M items
- **Index Size**: ~5-8 GB
- **Query Speed**: <50ms for most queries

---

## Best Practices

### 1. Incremental Analysis
```python
# Analyze in batches
for batch_start in range(0, total_bundles, 1000):
    analyzer.analyze(
        max_bundles=1000,
        skip_bundles=batch_start
    )
```

### 2. Memory Management
```python
# Use generators for large datasets
def iter_items(data_dir):
    for bundle in data_dir.glob("*.xz"):
        # Process and yield items
        # Memory-efficient
```

### 3. Caching Results
```python
# Cache expensive computations
import pickle

if cache_file.exists():
    report = pickle.load(cache_file.open("rb"))
else:
    report = analyzer.analyze()
    pickle.dump(report, cache_file.open("wb"))
```

---

## Integration with Other Tools

### Pandas
```python
import pandas as pd

# Load CSV export
df = pd.read_csv("hn_data.csv")

# Analyze
top_users = df.groupby("by")["id"].count().nlargest(10)
```

### DuckDB
```python
import duckdb

# Query directly
con = duckdb.connect()
results = con.execute("""
    SELECT by, COUNT(*) as count
    FROM read_csv_auto('hn_data.csv')
    GROUP BY by
    ORDER BY count DESC
    LIMIT 10
""").fetchall()
```

### Apache Spark
```python
from pyspark.sql import SparkSession

spark = SparkSession.builder.appName("HN Analysis").getOrCreate()

# Load JSONL
df = spark.read.json("comments.jsonl")

# Analyze at scale
df.groupBy("by").count().orderBy("count", ascending=False).show(10)
```

---

## Troubleshooting

### Issue: Out of Memory

**Solution:**
```python
# Process in smaller batches
analyzer.analyze(max_bundles=100)

# Or use streaming approach
for bundle in bundles:
    process_bundle(bundle)
    # Clear memory periodically
```

### Issue: Slow Search Queries

**Solution:**
```bash
# Optimize SQLite
sqlite3 hn_search.db "PRAGMA optimize;"
sqlite3 hn_search.db "VACUUM;"
```

### Issue: Corrupt Bundle Detection

**Solution:**
```python
validator = DataValidator(data_dir)
report = validator.validate()

# Re-download corrupt bundles
for corrupt in report.corrupt_bundles:
    re_download_bundle(corrupt)
```

---

## CLI Tools

All analytics features available via CLI:

```bash
# Statistics
python3 -m hnexport.analytics.stats hn/item --output stats.json

# Export
python3 -m hnexport.analytics.export hn/item --format sqlite --output hn.db

# Search
python3 -m hnexport.analytics.search hn_search.db "python async"

# Validate
python3 -m hnexport.analytics.validate hn/item
```

---

### 6. User Network Graph Generator (`network.py`)

Build network graphs showing user interactions and community structure.

**Features:**
- User interaction graphs (who replies to whom)
- Story-comment thread graphs
- Centrality metrics (degree, betweenness)
- Community detection
- Ego network extraction
- Export to multiple formats (GEXF, GraphML, JSON)

**Requirements:**
```bash
pip install networkx
pip install python-louvain  # For community detection
```

**Usage:**
```python
from hnexport.analytics import NetworkGraphBuilder

builder = NetworkGraphBuilder(data_dir=Path("hn/item"))

# Build user interaction graph
graph = builder.build_user_interaction_graph(
    max_bundles=1000,  # Sample for demo
    min_interactions=2  # Minimum replies to include edge
)

# Analyze graph
stats = builder.analyze_graph(graph, top_n=20)
print(f"Network: {stats.total_nodes:,} users, {stats.total_edges:,} interactions")
print(f"Top users by centrality:")
for user, metrics in stats.top_users[:10]:
    print(f"  {user}: {metrics['degree']:.4f}")

# Export graph
builder.export_graph(graph, Path("user_network.gexf"), format="gexf")

# Find communities
communities = builder.find_communities(graph, algorithm="louvain")
print(f"Found {len(set(communities.values()))} communities")

# Extract ego network for specific user
ego = builder.get_user_ego_network(graph, "pg", radius=2)
```

**Visualization:**
```python
# Visualize with networkx (requires matplotlib)
import matplotlib.pyplot as plt
import networkx as nx

# Draw top subgraph
top_users = [user for user, _ in stats.top_users[:50]]
subgraph = graph.subgraph(top_users)

pos = nx.spring_layout(subgraph)
nx.draw(subgraph, pos, with_labels=True, node_size=50, font_size=8)
plt.savefig("network.png")
```

---

### 7. Incremental Updater (`incremental.py`)

Efficiently download only new items since last update.

**Features:**
- Auto-detect highest local ID
- Download only new items
- Track update metadata
- Schedule recommendations
- Update specific items

**Usage:**
```python
import asyncio
from hnexport.analytics import IncrementalUpdater

async def update():
    updater = IncrementalUpdater(data_dir=Path("hn"))

    # Perform incremental update
    report = await updater.update()

    print(report)
    # Output:
    # Incremental Update Complete
    #   Range: 45,961,214 to 45,965,000
    #   New Items: 3,786
    #   Updated Items: 0
    #   Time: 45.2s (83.7 items/sec)

    # Get schedule recommendation
    schedule = updater.get_update_schedule_recommendation()
    print(f"Recommended: {schedule}")

asyncio.run(update())
```

**CLI:**
```bash
# Run incremental update
python3 -m hnexport.analytics.incremental hn/

# With custom start ID
python3 -m hnexport.analytics.incremental hn/ --start-id 45000000
```

**Automation:**
```bash
# Add to cron for daily updates
0 2 * * * cd /opt/hnexport && python3 -m hnexport.analytics.incremental hn/ >> update.log 2>&1
```

---

### 8. Real-time Monitor (`monitor.py`)

Monitor HackerNews in real-time for new items matching filters.

**Features:**
- Keyword filtering
- Author filtering
- Domain filtering
- Regex pattern matching
- Score threshold filtering
- Customizable poll interval

**Usage:**
```python
import asyncio
from hnexport.analytics import RealtimeMonitor, MonitorFilter
from hnexport.models import HNItem

def on_match(item: HNItem):
    """Called when item matches filter."""
    print(f"\n{'='*60}")
    print(f"[{item.type}] {item.title or item.text[:50]}")
    print(f"By: {item.by} | Score: {item.score}")
    print(f"https://news.ycombinator.com/item?id={item.id}")

async def monitor():
    monitor = RealtimeMonitor(poll_interval=10.0)

    # Add filters
    monitor.add_filter(MonitorFilter(
        keywords=["python", "async", "asyncio"],
        min_score=10
    ))

    monitor.add_filter(MonitorFilter(
        authors=["pg", "dang"],
    ))

    monitor.add_filter(MonitorFilter(
        domains=["github.com"],
        item_types=["story"]
    ))

    # Start monitoring (runs until Ctrl+C)
    await monitor.start(on_match=on_match)

asyncio.run(monitor())
```

**CLI:**
```bash
# Monitor for keywords
python3 -m hnexport.analytics.monitor python async

# Output:
# ============================================================
# [story] Building async Python applications
# By: user123 | Score: 45
# HN: https://news.ycombinator.com/item?id=45961234
```

**Advanced Usage:**
```python
# Run for specific duration
await monitor.start(on_match=on_match, duration_seconds=3600)  # 1 hour

# Check recent items (historical)
matches = await monitor.get_recent_matches(lookback_items=1000)
print(f"Found {len(matches)} matching items in last 1000 items")
```

---

### 9. Comprehensive Report Generator (`report.py`)

Generate unified reports combining multiple analytics.

**Features:**
- Combines statistics, trends, and validation
- Multiple output formats (JSON, Markdown, HTML)
- Quick sampling reports
- Customizable components

**Usage:**
```python
from hnexport.analytics import ReportGenerator

generator = ReportGenerator(data_dir=Path("hn/item"))

# Generate full report
report = generator.generate_full_report(
    include_stats=True,
    include_trends=True,
    include_validation=True,
    max_bundles=1000,  # Sample for demo
    trend_window_days=30,
)

# Export to different formats
from pathlib import Path

# JSON format
Path("report.json").write_text(report.to_json())

# Markdown format
Path("report.md").write_text(report.to_markdown())

# HTML format
Path("report.html").write_text(report.to_html())

# Quick report (stats only, sampled)
quick_report = generator.generate_quick_report(sample_bundles=100)
print(quick_report.to_markdown())
```

**CLI:**
```bash
# Generate report
python3 -m hnexport.analytics.report hn/item report.md markdown

# Generate JSON report
python3 -m hnexport.analytics.report hn/item report.json json
```

**Report Example:**
```markdown
# HackerNews Analytics Report

**Generated:** 2025-01-18T10:30:00
**Data Directory:** hn/item

## Summary

- **Total Items:** 45,961,213
- **Total Bundles:** 459,612
- **Unique Users:** 1,234,567
- **Date Range:** 2006-10-09 to 2025-01-18

## Statistics

- **Total Items:** 45,961,213
- **Total Bundles:** 459,612
- **Unique Users:** 1,234,567

### By Type

- **story:** 12,345,678
- **comment:** 32,456,789
- **job:** 567,890

### Top Submitters

- **pg:** 12,345
- **dang:** 10,234
...
```

---

## Complete Example: Full Analytics Pipeline

```python
#!/usr/bin/env python3
"""Complete analytics pipeline demonstrating all features."""

import asyncio
import json
from pathlib import Path
from hnexport.analytics import (
    StatsAnalyzer,
    TrendAnalyzer,
    DataValidator,
    DataExporter,
    SearchIndex,
    NetworkGraphBuilder,
    IncrementalUpdater,
    ReportGenerator,
)

async def main():
    data_dir = Path("hn/item")

    # 1. Incremental update
    print("1. Checking for updates...")
    updater = IncrementalUpdater(Path("hn"))
    update_report = await updater.update()
    print(update_report)

    # 2. Validate data
    print("\n2. Validating data...")
    validator = DataValidator(data_dir)
    validation = validator.validate(check_schema=True)
    print(f"Valid: {validation.valid_bundles}/{validation.total_bundles}")

    # 3. Generate statistics
    print("\n3. Generating statistics...")
    stats = StatsAnalyzer(data_dir).analyze(max_bundles=1000)
    print(f"Analyzed {stats.total_items:,} items")

    # 4. Analyze trends
    print("\n4. Analyzing trends...")
    trends = TrendAnalyzer(data_dir).analyze_trends(time_window_days=30)
    print(f"Top keywords: {trends.trending_keywords[:5]}")

    # 5. Build network graph
    print("\n5. Building network graph...")
    network = NetworkGraphBuilder(data_dir)
    graph = network.build_user_interaction_graph(max_bundles=500)
    graph_stats = network.analyze_graph(graph)
    print(f"Network: {graph_stats.total_nodes} users, {graph_stats.total_edges} edges")

    # 6. Build search index
    print("\n6. Building search index...")
    search = SearchIndex(data_dir)
    search.build(Path("hn_search.db"), max_bundles=500)

    # 7. Export to SQLite
    print("\n7. Exporting to SQLite...")
    exporter = DataExporter(data_dir)
    count = exporter.export_to_sqlite(
        Path("hn.db"),
        max_bundles=500,
        create_indexes=True
    )
    print(f"Exported {count:,} items")

    # 8. Generate comprehensive report
    print("\n8. Generating report...")
    generator = ReportGenerator(data_dir)
    report = generator.generate_full_report(max_bundles=1000)
    Path("comprehensive_report.json").write_text(report.to_json())
    Path("comprehensive_report.md").write_text(report.to_markdown())

    print("\n✓ Complete! All analytics generated.")
    print(f"  - Database: hn.db")
    print(f"  - Search index: hn_search.db")
    print(f"  - Reports: comprehensive_report.{json,md}")

if __name__ == "__main__":
    asyncio.run(main())
```

---

## Future Enhancements

Planned features:
- **Machine Learning Classifier**: Auto-categorize content
- **Sentiment Analyzer**: Track sentiment trends
- **Web Dashboard**: Visual analytics interface
- **API Server**: REST API over data
- **Elasticsearch Integration**: Advanced search
- **Time-series Database Export**: InfluxDB/TimescaleDB
- **LLM Integration**: Semantic search and summarization

---

## Contributing

Want to add more analytics features? See the contribution guide!
