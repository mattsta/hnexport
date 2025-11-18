# HNexport Use Cases & Examples

## Table of Contents
- [Basic Usage](#basic-usage)
- [Advanced Patterns](#advanced-patterns)
- [Data Analysis](#data-analysis)
- [Production Deployments](#production-deployments)
- [Research Applications](#research-applications)
- [Troubleshooting](#troubleshooting)

---

## Basic Usage

### 1. Download All HN Items (Beginner)

**Goal**: Get a complete archive of HackerNews

```bash
# Simple download to default directory (./hn)
hnexport --items

# With custom output location
hnexport --items --output /mnt/data/hn-archive

# Check progress in another terminal
tail -f hnexport.log
```

**Expected Results:**
- Directory: `hn/item/`
- Files: `0-99.xz`, `100-199.xz`, etc.
- Size: ~4-5 GB compressed
- Duration: ~4-6 hours (single process, 50 concurrency)

**Resume Capability:**
```bash
# Download interrupted? Just run again!
hnexport --items --output /mnt/data/hn-archive
# Automatically skips existing bundles
```

---

### 2. High-Speed Download with Multiprocessing

**Goal**: Download as fast as possible

```bash
# Use all CPU cores
hnexport --items --multiprocess

# Specify worker count
hnexport --items --multiprocess --workers 8

# Adjust concurrency per worker
export HNEXPORT_MAX_CONCURRENT=100
hnexport --items --multiprocess --workers 4
```

**Performance Comparison:**
```
Single process (50 concurrent):  ~100 items/sec  → 4-6 hours
Multiprocess (4 workers):        ~300 items/sec  → 1.5-2 hours
Multiprocess (8 workers):        ~500 items/sec  → 1-1.5 hours
```

---

### 3. Download Specific Users

**Goal**: Get profile data for specific HN users

```bash
# Create username list
cat > usernames.txt <<EOF
pg
dang
tptacek
patio11
EOF

# Download user profiles
hnexport --users usernames.txt

# Results in hn/user/
ls hn/user/
# pg.json  dang.json  tptacek.json  patio11.json
```

**Extract Users from Items:**
```bash
# Use the helper script
./slow_bulk_usernames.sh > all_usernames.txt

# Download all users
hnexport --users all_usernames.txt
```

---

## Advanced Patterns

### 4. Incremental Updates (Cron Job)

**Goal**: Keep archive up-to-date with daily downloads

```bash
#!/bin/bash
# cron-update-hn.sh

# Get current highest ID
PREV_HIGH=$(cat ~/.hnexport_last_id 2>/dev/null || echo "0")

# Download using Python API
python3 <<EOF
import asyncio
from hnexport import HackerNewsClient, HNDownloader
from pathlib import Path

async def incremental_update():
    downloader = HNDownloader(output_dir=Path("/data/hn"))

    async with HackerNewsClient() as client:
        current_high = await client.get_highest_item_id()

    # Save for next run
    with open(Path.home() / ".hnexport_last_id", "w") as f:
        f.write(str(current_high))

    print(f"Updated to item {current_high}")

asyncio.run(incremental_update())
EOF
```

**Cron Schedule:**
```cron
# Run daily at 2 AM
0 2 * * * /path/to/cron-update-hn.sh >> /var/log/hnexport-cron.log 2>&1
```

---

### 5. Custom Concurrency Tuning

**Goal**: Optimize for your network/hardware

```bash
# Low bandwidth - conservative
export HNEXPORT_MAX_CONCURRENT=10
hnexport --items

# High bandwidth - aggressive
export HNEXPORT_MAX_CONCURRENT=200
hnexport --items

# Auto-detect optimal (heuristic)
CORES=$(nproc)
export HNEXPORT_MAX_CONCURRENT=$((CORES * 25))
hnexport --items --multiprocess --workers $CORES
```

**Tuning Guidelines:**
- **Slow network** (< 10 Mbps): 10-20 concurrent
- **Normal network** (10-100 Mbps): 50-100 concurrent
- **Fast network** (> 100 Mbps): 100-200 concurrent
- **Server/Datacenter**: 200-500 concurrent

---

### 6. Python API - Custom Filtering

**Goal**: Download only specific item types

```python
import asyncio
from hnexport import HackerNewsClient
from pathlib import Path
import json

async def download_only_stories():
    """Download and filter only story items."""
    output_dir = Path("hn_stories_only")
    output_dir.mkdir(exist_ok=True)

    async with HackerNewsClient() as client:
        # Get range
        highest = await client.get_highest_item_id()

        # Process in batches
        batch_size = 1000
        for start in range(0, highest, batch_size):
            end = min(start + batch_size, highest)
            item_ids = list(range(start, end))

            # Fetch batch
            items = await client.get_items_batch(item_ids)

            # Filter for stories
            stories = [
                item for item in items
                if item and item.type == "story"
            ]

            # Save stories
            for story in stories:
                story_file = output_dir / f"{story.id}.json"
                story_file.write_text(
                    json.dumps(story.to_dict(), indent=2)
                )

            print(f"Processed {start}-{end}: {len(stories)} stories")

asyncio.run(download_only_stories())
```

---

### 7. Real-time Monitoring

**Goal**: Track download progress programmatically

```python
import asyncio
from hnexport import HNDownloader
from pathlib import Path
import time

async def download_with_monitoring():
    """Download with custom progress monitoring."""
    downloader = HNDownloader(output_dir=Path("hn"))

    # Start download in background
    task = asyncio.create_task(downloader.download_all_items())

    # Monitor progress
    while not task.done():
        stats = downloader.stats
        if stats.total_items > 0:
            progress = (stats.successful / stats.total_items) * 100
            rate = stats.items_per_second

            print(
                f"\rProgress: {progress:.1f}% | "
                f"Rate: {rate:.0f} items/sec | "
                f"Bundles: {stats.bundles_created}",
                end="",
                flush=True
            )

        await asyncio.sleep(1)

    # Get final stats
    stats = await task
    print(f"\n\nComplete! Downloaded {stats.successful:,} items in {stats.duration:.0f}s")

asyncio.run(download_with_monitoring())
```

---

## Data Analysis

### 8. Top Submitters Analysis

```python
import json
import lzma
from pathlib import Path
from collections import Counter

def analyze_top_submitters(data_dir="hn/item"):
    """Find users with most submissions."""
    submitters = Counter()

    # Process all bundles
    for bundle in sorted(Path(data_dir).glob("*.xz")):
        with lzma.open(bundle, "rt") as f:
            # Parse concatenated JSON
            items_text = f.read()
            for line in items_text.strip().split("\n"):
                if line and line != "null":
                    item = json.loads(line)
                    if item.get("type") in ["story", "job", "poll"]:
                        submitters[item.get("by", "unknown")] += 1

    # Top 20 submitters
    for user, count in submitters.most_common(20):
        print(f"{user:20s} {count:6d} submissions")

analyze_top_submitters()
```

---

### 9. Sentiment Analysis Pipeline

```python
import asyncio
from hnexport import HackerNewsClient
import json
from datetime import datetime

async def analyze_sentiment_over_time():
    """Analyze comment sentiment by time period."""
    async with HackerNewsClient() as client:
        # Get recent items
        highest = await client.get_highest_item_id()
        recent_ids = range(highest - 10000, highest)

        items = await client.get_items_batch(list(recent_ids))

        # Filter comments
        comments = [
            item for item in items
            if item and item.type == "comment" and item.text
        ]

        # Group by month
        by_month = {}
        for comment in comments:
            if comment.time:
                month = datetime.fromtimestamp(comment.time).strftime("%Y-%m")
                if month not in by_month:
                    by_month[month] = []
                by_month[month].append(comment.text)

        # Analyze (placeholder - add your sentiment library)
        for month, texts in sorted(by_month.items()):
            avg_length = sum(len(t) for t in texts) / len(texts)
            print(f"{month}: {len(texts)} comments, avg length {avg_length:.0f} chars")

asyncio.run(analyze_sentiment_over_time())
```

---

### 10. Export to Different Formats

```python
import json
import lzma
import csv
from pathlib import Path

def export_to_csv(bundle_path, output_csv):
    """Convert HN bundle to CSV format."""
    with lzma.open(bundle_path, "rt") as f:
        items_text = f.read()

    items = [
        json.loads(line)
        for line in items_text.strip().split("\n")
        if line and line != "null"
    ]

    # CSV export
    with open(output_csv, "w", newline="") as csvfile:
        fieldnames = ["id", "type", "by", "time", "score", "title", "url"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames, extrasaction="ignore")

        writer.writeheader()
        for item in items:
            writer.writerow(item)

# Example
export_to_csv("hn/item/0-99.xz", "hn_first_100.csv")
```

---

## Production Deployments

### 11. Docker Container

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY hnexport/ ./hnexport/
COPY pyproject.toml .

# Install package
RUN pip install -e .

# Create data directory
VOLUME /data

# Environment defaults
ENV HNEXPORT_OUTPUT_DIR=/data/hn
ENV HNEXPORT_LOG_LEVEL=INFO

ENTRYPOINT ["python", "-m", "hnexport.cli"]
```

```bash
# Build
docker build -t hnexport:v2 .

# Run
docker run -v /mnt/data:/data hnexport:v2 --items

# With custom config
docker run \
  -e HNEXPORT_MAX_CONCURRENT=100 \
  -e HNEXPORT_LOG_LEVEL=DEBUG \
  -v /mnt/data:/data \
  hnexport:v2 --items --multiprocess --workers 8
```

---

### 12. Kubernetes CronJob

```yaml
# hn-download-cronjob.yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: hnexport-daily
spec:
  schedule: "0 2 * * *"  # Daily at 2 AM
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: hnexport
            image: hnexport:v2
            args: ["--items", "--multiprocess", "--workers", "4"]
            env:
            - name: HNEXPORT_OUTPUT_DIR
              value: /data/hn
            - name: HNEXPORT_MAX_CONCURRENT
              value: "100"
            volumeMounts:
            - name: data-volume
              mountPath: /data
            resources:
              requests:
                memory: "2Gi"
                cpu: "2"
              limits:
                memory: "4Gi"
                cpu: "4"
          volumes:
          - name: data-volume
            persistentVolumeClaim:
              claimName: hn-data-pvc
          restartPolicy: OnFailure
```

---

### 13. AWS Lambda (Serverless)

```python
# lambda_handler.py
import asyncio
from hnexport import HackerNewsClient, HNDownloader
from pathlib import Path
import boto3

async def download_chunk(start_id, end_id, s3_bucket):
    """Download chunk and upload to S3."""
    downloader = HNDownloader(output_dir=Path("/tmp/hn"))

    async with HackerNewsClient() as client:
        await downloader.download_item_range(start_id, end_id, client=client)

    # Upload to S3
    s3 = boto3.client('s3')
    for bundle in Path("/tmp/hn/item").glob("*.xz"):
        s3.upload_file(
            str(bundle),
            s3_bucket,
            f"hn/item/{bundle.name}"
        )

def lambda_handler(event, context):
    """Lambda entry point."""
    start_id = event['start_id']
    end_id = event['end_id']
    s3_bucket = event['s3_bucket']

    asyncio.run(download_chunk(start_id, end_id, s3_bucket))

    return {
        'statusCode': 200,
        'body': f'Downloaded items {start_id}-{end_id}'
    }
```

---

## Research Applications

### 14. Natural Language Processing Dataset

```python
async def create_nlp_dataset():
    """Extract text corpus for NLP training."""
    async with HackerNewsClient() as client:
        highest = await client.get_highest_item_id()

        corpus_file = open("hn_corpus.txt", "w")

        # Process in batches
        for start in range(0, highest, 5000):
            items = await client.get_items_batch(
                list(range(start, start + 5000))
            )

            # Extract text from comments and stories
            for item in items:
                if not item:
                    continue

                text = None
                if item.text:  # Comment
                    text = item.text
                elif item.title:  # Story
                    text = item.title

                if text:
                    # Clean HTML
                    import html
                    clean_text = html.unescape(text)
                    corpus_file.write(clean_text + "\n\n")

            print(f"Processed {start:,} items")

        corpus_file.close()

asyncio.run(create_nlp_dataset())
```

---

### 15. Social Network Graph Construction

```python
import networkx as nx
from hnexport import HackerNewsClient
import asyncio

async def build_interaction_graph():
    """Build user interaction graph from comments."""
    G = nx.DiGraph()

    async with HackerNewsClient() as client:
        # Get sample of recent items
        highest = await client.get_highest_item_id()
        sample_ids = range(highest - 100000, highest)

        items = await client.get_items_batch(list(sample_ids))

        # Build graph
        for item in items:
            if not item or item.type != "comment":
                continue

            author = item.by
            if not author:
                continue

            # Get parent to find who they're replying to
            if item.parent:
                parent_item = await client.get_item(item.parent)
                if parent_item and parent_item.by:
                    # Add edge: author -> parent_author
                    G.add_edge(author, parent_item.by)

        # Analyze
        print(f"Nodes (users): {G.number_of_nodes()}")
        print(f"Edges (interactions): {G.number_of_edges()}")

        # Top influencers (by in-degree)
        in_degrees = dict(G.in_degree())
        top_influencers = sorted(
            in_degrees.items(),
            key=lambda x: x[1],
            reverse=True
        )[:10]

        print("\nTop Influencers:")
        for user, replies in top_influencers:
            print(f"  {user}: {replies} replies received")

        # Save graph
        nx.write_gexf(G, "hn_interaction_graph.gexf")

asyncio.run(build_interaction_graph())
```

---

## Troubleshooting

### 16. Debugging Failed Downloads

```bash
# Enable debug logging
export HNEXPORT_LOG_LEVEL=DEBUG
export HNEXPORT_LOG_FILE=true
hnexport --items

# Check log for errors
grep ERROR hnexport.log

# Test single item fetch
python3 <<EOF
import asyncio
from hnexport import HackerNewsClient

async def test():
    async with HackerNewsClient() as client:
        item = await client.get_item(1)
        print(f"Success: {item}")

asyncio.run(test())
EOF
```

---

### 17. Verify Data Integrity

```python
import lzma
import json
from pathlib import Path

def verify_bundles(data_dir="hn/item"):
    """Check all bundles for corruption."""
    bundles = sorted(Path(data_dir).glob("*.xz"))

    for bundle in bundles:
        try:
            with lzma.open(bundle, "rt") as f:
                content = f.read()
                lines = [l for l in content.split("\n") if l]

                # Parse each JSON
                valid_count = 0
                for line in lines:
                    if line != "null":
                        json.loads(line)  # Will raise if invalid
                        valid_count += 1

                print(f"✓ {bundle.name}: {valid_count} valid items")

        except Exception as e:
            print(f"✗ {bundle.name}: ERROR - {e}")

verify_bundles()
```

---

### 18. Network Diagnostics

```python
import asyncio
import time
from hnexport import HackerNewsClient

async def benchmark_api():
    """Measure API performance."""
    async with HackerNewsClient(max_concurrent=10) as client:
        # Test latency
        start = time.time()
        await client.get_item(1)
        latency = time.time() - start
        print(f"Single request latency: {latency*1000:.0f}ms")

        # Test throughput
        test_ids = list(range(1, 101))
        start = time.time()
        items = await client.get_items_batch(test_ids)
        duration = time.time() - start

        rate = len(items) / duration
        print(f"Batch throughput: {rate:.1f} items/sec")
        print(f"Optimal concurrency: ~{int(rate * 0.5)}-{int(rate)}")

asyncio.run(benchmark_api())
```

---

## Performance Benchmarking

### 19. Measure Download Speed

```bash
#!/bin/bash
# benchmark.sh - Test different configurations

echo "=== HNexport Performance Benchmark ==="

# Test 1: Single process, low concurrency
echo -e "\nTest 1: Single process, 10 concurrent"
export HNEXPORT_MAX_CONCURRENT=10
time python3 -m hnexport.cli --items --output /tmp/hn-test1 2>&1 | grep "items/sec"

# Test 2: Single process, high concurrency
echo -e "\nTest 2: Single process, 100 concurrent"
export HNEXPORT_MAX_CONCURRENT=100
time python3 -m hnexport.cli --items --output /tmp/hn-test2 2>&1 | grep "items/sec"

# Test 3: Multiprocessing
echo -e "\nTest 3: Multiprocessing, 4 workers"
time python3 -m hnexport.cli --items --multiprocess --workers 4 --output /tmp/hn-test3 2>&1 | grep "items/sec"

echo -e "\n=== Benchmark Complete ==="
```
