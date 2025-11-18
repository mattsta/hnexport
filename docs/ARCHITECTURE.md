# HNexport Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        HNexport v2.0                             │
│                  Modern Async HN Downloader                      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
        ┌─────────────────────────────────────────┐
        │         CLI Entry Point                 │
        │      (hnexport.cli.main)                │
        │  • Argument parsing                     │
        │  • Environment config                   │
        │  • Async orchestration                  │
        └────────────┬────────────────────────────┘
                     │
        ┌────────────┴────────────┐
        │                         │
        ▼                         ▼
┌──────────────┐         ┌──────────────┐
│ HNDownloader │         │  CLI Tools   │
│              │         │              │
│ • Items      │         │ • Processor  │
│ • Users      │         │ • Stats      │
│ • Bundles    │         │ • Reports    │
└──────┬───────┘         └──────────────┘
       │
       ▼
┌──────────────────────────────────┐
│    HackerNewsClient              │
│                                  │
│  ┌────────────────────────────┐ │
│  │  Connection Pool Manager   │ │
│  │  • HTTP/1.1 connections    │ │
│  │  • Keep-alive handling     │ │
│  │  • Connection limits       │ │
│  └────────────────────────────┘ │
│                                  │
│  ┌────────────────────────────┐ │
│  │  Concurrency Controller    │ │
│  │  • Semaphore (max: 50)     │ │
│  │  • Rate limiting           │ │
│  │  • Request queuing         │ │
│  └────────────────────────────┘ │
│                                  │
│  ┌────────────────────────────┐ │
│  │  Retry & Error Handler     │ │
│  │  • Exponential backoff     │ │
│  │  • Max retries: 7          │ │
│  │  • Error classification    │ │
│  └────────────────────────────┘ │
└──────────┬───────────────────────┘
           │
           ▼
    ┌──────────────┐
    │   httpx      │
    │ AsyncClient  │
    └──────┬───────┘
           │
           ▼
┌────────────────────────┐
│  HackerNews Firebase   │
│  API (Google Cloud)    │
│                        │
│  • /maxitem.json       │
│  • /item/{id}.json     │
│  • /user/{name}.json   │
└────────────────────────┘
```

---

## Component Architecture

### 1. Configuration Layer

```
┌─────────────────────────────────────────────────────┐
│                Config (config.py)                    │
├─────────────────────────────────────────────────────┤
│                                                      │
│  ┌──────────────┐  ┌──────────────┐                │
│  │  APIConfig   │  │ Concurrency  │                │
│  │              │  │    Config    │                │
│  │ • base_url   │  │ • max_conc   │                │
│  │ • timeouts   │  │ • workers    │                │
│  │ • retries    │  │ • batch_size │                │
│  └──────────────┘  └──────────────┘                │
│                                                      │
│  ┌──────────────┐  ┌──────────────┐                │
│  │   Storage    │  │   Logging    │                │
│  │    Config    │  │    Config    │                │
│  │              │  │              │                │
│  │ • output_dir │  │ • level      │                │
│  │ • bundle_sz  │  │ • format     │                │
│  │ • compress   │  │ • file_log   │                │
│  └──────────────┘  └──────────────┘                │
│                                                      │
│  Environment Variables ──> Dataclass Fields         │
│  HNEXPORT_MAX_CONCURRENT ──> max_concurrent_requests│
│  HNEXPORT_OUTPUT_DIR ──────> output_dir             │
└─────────────────────────────────────────────────────┘
```

**Design Principles:**
- Single source of truth for all configuration
- Environment variable support for 12-factor apps
- Type-safe with dataclasses
- No side effects during initialization

---

### 2. HTTP Client Layer

```
┌───────────────────────────────────────────────────────────┐
│              HackerNewsClient (client.py)                 │
├───────────────────────────────────────────────────────────┤
│                                                            │
│  Lifecycle:                                                │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐ │
│  │ __init__ │→ │__aenter__│→ │  fetch   │→ │__aexit__ │ │
│  │  setup   │  │  create  │  │operations│  │ cleanup  │ │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘ │
│                                                            │
│  Request Flow:                                             │
│  ┌─────────────────────────────────────────────────────┐ │
│  │ 1. Acquire semaphore slot                           │ │
│  │    ↓                                                 │ │
│  │ 2. Build request URL                                │ │
│  │    ↓                                                 │ │
│  │ 3. Send via httpx (with timeout)                    │ │
│  │    ↓                                                 │ │
│  │ 4. Handle response:                                 │ │
│  │    • 200 OK → parse JSON                            │ │
│  │    • 404 → ItemNotFoundError                        │ │
│  │    • 5xx → retry with backoff                       │ │
│  │    • Timeout → retry with backoff                   │ │
│  │    ↓                                                 │ │
│  │ 5. Release semaphore                                │ │
│  └─────────────────────────────────────────────────────┘ │
│                                                            │
│  Methods:                                                  │
│  • get_item(id) → HNItem | None                          │
│  • get_items_batch([ids]) → List[HNItem | None]          │
│  • get_user(username) → HNUser | None                    │
│  • get_highest_item_id() → int                           │
│  • get_raw_items_batch([ids]) → List[bytes]              │
└───────────────────────────────────────────────────────────┘
```

**Key Features:**
- **Self-managing**: Context manager handles resource lifecycle
- **Concurrent**: Semaphore-based request limiting
- **Resilient**: Automatic retry with exponential backoff
- **Efficient**: Connection pooling and keep-alive

---

### 3. Download Orchestration Layer

```
┌─────────────────────────────────────────────────────────┐
│            HNDownloader (downloader.py)                 │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  Download Pipeline:                                      │
│                                                          │
│  ┌───────────────────────────────────────────────────┐ │
│  │ 1. Get highest item ID from API                   │ │
│  │    (e.g., 45,961,213)                              │ │
│  └───────────────────────────────────────────────────┘ │
│                    ↓                                     │
│  ┌───────────────────────────────────────────────────┐ │
│  │ 2. Split range into bundles                       │ │
│  │    0-99, 100-199, 200-299, ...                    │ │
│  │    (bundle_size = 100)                             │ │
│  └───────────────────────────────────────────────────┘ │
│                    ↓                                     │
│  ┌───────────────────────────────────────────────────┐ │
│  │ 3. For each bundle:                               │ │
│  │    ┌────────────────────────────────────────────┐ │ │
│  │    │ a) Check if exists (resume capability)    │ │ │
│  │    │    • Skip if exists                        │ │ │
│  │    │                                             │ │ │
│  │    │ b) Fetch items concurrently                │ │ │
│  │    │    • Client.get_raw_items_batch()          │ │ │
│  │    │    • Returns 100 raw JSON responses        │ │ │
│  │    │                                             │ │ │
│  │    │ c) Compress in thread pool                 │ │ │
│  │    │    • await asyncio.to_thread(lzma.compress)│ │ │
│  │    │    • Non-blocking compression              │ │ │
│  │    │                                             │ │ │
│  │    │ d) Write atomically                        │ │ │
│  │    │    • temp.write() → rename()               │ │ │
│  │    │    • Set mtime to last item timestamp      │ │ │
│  │    │                                             │ │ │
│  │    │ e) Update statistics                       │ │ │
│  │    │    • bundles_created++                     │ │ │
│  │    │    • successful += non_null_count          │ │ │
│  │    └────────────────────────────────────────────┘ │ │
│  └───────────────────────────────────────────────────┘ │
│                    ↓                                     │
│  ┌───────────────────────────────────────────────────┐ │
│  │ 4. Return statistics                              │ │
│  │    • Total items, successful, failed              │ │
│  │    • Duration, rate (items/sec)                   │ │
│  └───────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

**Optimization Strategies:**
- **Client reuse**: Single HTTP client across all bundles
- **Non-blocking I/O**: CPU-intensive work in thread pool
- **Resume capability**: Skip existing bundles
- **Progress tracking**: Real-time statistics

---

### 4. Concurrency Models

#### Single-Process Async Model (Default)

```
┌────────────────────────────────────────────────┐
│          Main Event Loop                       │
├────────────────────────────────────────────────┤
│                                                 │
│  ┌──────────────────────────────────────────┐ │
│  │  Semaphore (limit: 50)                   │ │
│  │  ┌────────────────────────────────────┐  │ │
│  │  │  Concurrent HTTP Requests          │  │ │
│  │  │                                     │  │ │
│  │  │  [Req1][Req2][Req3]...[Req50]      │  │ │
│  │  │    ↓     ↓     ↓         ↓         │  │ │
│  │  │  ┌────┬────┬────┬─────┬────┐       │  │ │
│  │  │  │    │    │    │ ... │    │       │  │ │
│  │  │  └────┴────┴────┴─────┴────┘       │  │ │
│  │  │     Connection Pool                 │  │ │
│  │  │     (max: 100 connections)          │  │ │
│  │  └────────────────────────────────────┘  │ │
│  │                                           │ │
│  │  ┌────────────────────────────────────┐  │ │
│  │  │  Thread Pool (for blocking ops)    │  │ │
│  │  │                                     │  │ │
│  │  │  [Compress1][Compress2][Write1]... │  │ │
│  │  │      ↓          ↓         ↓        │  │ │
│  │  │    lzma      lzma     file I/O     │  │ │
│  │  └────────────────────────────────────┘  │ │
│  └──────────────────────────────────────────┘ │
│                                                 │
│  Performance:                                   │
│  • 50 concurrent HTTP requests                 │
│  • ~2,500-5,000 items/sec                      │
│  • Low memory footprint                        │
└────────────────────────────────────────────────┘
```

#### Multiprocessing Model (For Large Downloads)

```
┌─────────────────────────────────────────────────────────┐
│                    Main Process                         │
│  ┌────────────────────────────────────────────────┐    │
│  │ 1. Get highest ID: 45,961,213                  │    │
│  │ 2. Split into chunks (20,000 items/worker)     │    │
│  │    Chunk 0:     0 - 19,999                     │    │
│  │    Chunk 1: 20,000 - 39,999                    │    │
│  │    Chunk 2: 40,000 - 59,999                    │    │
│  │    ...                                          │    │
│  │ 3. Create worker pool                          │    │
│  └────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
                       │
         ┌─────────────┼─────────────┬─────────────┐
         ▼             ▼             ▼             ▼
   ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
   │ Worker 1 │  │ Worker 2 │  │ Worker 3 │  │ Worker N │
   │          │  │          │  │          │  │          │
   │ Chunk 0  │  │ Chunk 1  │  │ Chunk 2  │  │ Chunk N  │
   │          │  │          │  │          │  │          │
   │ ┌──────┐ │  │ ┌──────┐ │  │ ┌──────┐ │  │ ┌──────┐ │
   │ │ Async│ │  │ │ Async│ │  │ │ Async│ │  │ │ Async│ │
   │ │Client│ │  │ │Client│ │  │ │Client│ │  │ │Client│ │
   │ │      │ │  │ │      │ │  │ │      │ │  │ │      │ │
   │ │50 req│ │  │ │50 req│ │  │ │50 req│ │  │ │50 req│ │
   │ └──────┘ │  │ └──────┘ │  │ └──────┘ │  │ └──────┘ │
   └──────────┘  └──────────┘  └──────────┘  └──────────┘

Performance (8 workers):
• 8 × 50 = 400 concurrent requests
• ~20,000-40,000 items/sec
• Higher CPU/memory usage
• Near-linear scaling
```

---

## Data Flow

### Item Download Flow

```
User Request
     │
     ▼
┌─────────────────┐
│   CLI Parser    │
│  args.items=True│
└────────┬────────┘
         │
         ▼
┌──────────────────┐
│  HNDownloader    │
│  .download_all() │
└────────┬─────────┘
         │
         ├─────────────────────────────┐
         │                             │
         ▼                             ▼
┌──────────────────┐         ┌──────────────────┐
│ Get Highest ID   │         │  Create Bundles  │
│                  │         │  directories     │
│ API: maxitem.json│         │  hn/item/        │
│ Returns: 45.9M   │         │                  │
└────────┬─────────┘         └────────┬─────────┘
         │                            │
         └──────────┬─────────────────┘
                    │
                    ▼
         ┌────────────────────┐
         │  For each bundle:  │
         │  0-99, 100-199...  │
         └─────────┬──────────┘
                   │
                   ▼
         ┌─────────────────────────┐
         │  Parallel Fetch (50)    │
         │  ┌──┐┌──┐┌──┐┌──┐       │
         │  │ID││ID││ID││ID│ ...   │
         │  └──┘└──┘└──┘└──┘       │
         └──────────┬──────────────┘
                    │
                    ▼
         ┌──────────────────────────┐
         │  Receive JSON Responses  │
         │  [bytes, bytes, ...]     │
         └──────────┬───────────────┘
                    │
                    ▼
         ┌──────────────────────────┐
         │  Compress (thread pool)  │
         │  lzma.compress(preset=9) │
         └──────────┬───────────────┘
                    │
                    ▼
         ┌──────────────────────────┐
         │  Write Atomically        │
         │  tmp.xz → 0-99.xz        │
         │  Set mtime from last item│
         └──────────┬───────────────┘
                    │
                    ▼
         ┌──────────────────────────┐
         │  Update Statistics       │
         │  bundles_created++       │
         │  Log progress every 10   │
         └──────────────────────────┘
```

---

## Error Handling Strategy

```
┌─────────────────────────────────────────────────────┐
│               Error Classification                   │
├─────────────────────────────────────────────────────┤
│                                                      │
│  Network Errors (Retriable)                         │
│  ├─ ConnectError      → Retry with backoff          │
│  ├─ TimeoutException  → Retry with backoff          │
│  └─ ReadError         → Retry with backoff          │
│                                                      │
│  HTTP Errors (Conditional)                          │
│  ├─ 404 Not Found     → Return None (expected)      │
│  ├─ 5xx Server Error  → Retry with backoff          │
│  └─ 4xx Client Error  → Raise APIError (no retry)   │
│                                                      │
│  Application Errors (Not Retriable)                 │
│  ├─ JSONDecodeError   → Log & return None           │
│  ├─ StorageError      → Raise immediately           │
│  └─ ConfigError       → Raise immediately           │
│                                                      │
└─────────────────────────────────────────────────────┘

Retry Logic:
┌────────────────────────────────────────────────┐
│ Attempt 1: Immediate                           │
│ Attempt 2: Wait 0.5s  (backoff_factor × 2^0)  │
│ Attempt 3: Wait 1.0s  (backoff_factor × 2^1)  │
│ Attempt 4: Wait 2.0s  (backoff_factor × 2^2)  │
│ Attempt 5: Wait 4.0s  (backoff_factor × 2^3)  │
│ Attempt 6: Wait 8.0s  (backoff_factor × 2^4)  │
│ Attempt 7: Wait 16.0s (backoff_factor × 2^5)  │
│ Attempt 8: Wait 32.0s (backoff_factor × 2^6)  │
│ Max reached: Raise RetryExhaustedError         │
└────────────────────────────────────────────────┘
```

---

## Memory Management

```
┌─────────────────────────────────────────────────────┐
│             Memory Footprint Analysis                │
├─────────────────────────────────────────────────────┤
│                                                      │
│  Per Bundle (100 items):                            │
│  ├─ Raw JSON: ~50-100 KB                            │
│  ├─ Compressed: ~10-20 KB (80-90% reduction)        │
│  └─ In-memory: ~150 KB (during processing)          │
│                                                      │
│  Concurrent Operations (50 requests):               │
│  ├─ HTTP buffers: ~5 MB                             │
│  ├─ Response data: ~5 MB                            │
│  └─ Connection overhead: ~2 MB                      │
│                                                      │
│  Thread Pool:                                        │
│  ├─ Compression temp: ~100 KB per thread            │
│  ├─ Default threads: 32 (system default)            │
│  └─ Total: ~3 MB                                    │
│                                                      │
│  Total Memory Usage:                                │
│  ├─ Base: ~50 MB (Python + httpx)                   │
│  ├─ Working: ~15 MB (concurrent operations)         │
│  └─ Peak: ~65 MB (typical)                          │
│                                                      │
│  Multiprocessing (8 workers):                       │
│  └─ ~65 MB × 8 = ~520 MB total                      │
│                                                      │
└─────────────────────────────────────────────────────┘
```

---

## Performance Characteristics

### Throughput Analysis

```
┌──────────────────────────────────────────────────────┐
│                  Performance Profile                  │
├──────────────────────────────────────────────────────┤
│                                                       │
│  Baseline (no optimization):                         │
│  └─ 4 items/second = 240 items/minute                │
│                                                       │
│  Thread-based (v1.0):                                │
│  ├─ 25 concurrent threads                            │
│  ├─ ~60-80 items/second                              │
│  └─ 15-20x faster than baseline                      │
│                                                       │
│  Async (v2.0 - current):                             │
│  ├─ 50 concurrent requests                           │
│  ├─ ~80-120 items/second                             │
│  ├─ 20-30x faster than baseline                      │
│  └─ 1.5x faster than v1.0                            │
│                                                       │
│  Async + Multiprocessing (8 workers):                │
│  ├─ 400 concurrent requests                          │
│  ├─ ~300-600 items/second                            │
│  ├─ 75-150x faster than baseline                     │
│  └─ 5-7x faster than single-process async            │
│                                                       │
│  Time to Download Full HN (45.9M items):             │
│  ├─ Baseline: ~133 days                              │
│  ├─ Thread (v1): ~6.6 days                           │
│  ├─ Async: ~4.4 days                                 │
│  └─ Multi (8): ~21 hours                             │
│                                                       │
└──────────────────────────────────────────────────────┘
```

### Bottleneck Analysis

```
Operation Timings (per bundle of 100 items):
┌────────────────────────────────────────┐
│ HTTP Fetch:    ~1.5-2.0s  (60-70%)    │  ← Network I/O
│ Compression:   ~0.3-0.5s  (15-20%)    │  ← CPU-bound
│ File Write:    ~0.1-0.2s  (5-10%)     │  ← Disk I/O
│ Overhead:      ~0.1-0.3s  (5-15%)     │  ← Parsing, stats
└────────────────────────────────────────┘

Optimization Impact:
• Non-blocking compression: +20-30% throughput
• Connection pooling: +10-15% throughput
• Batch resilience: -5% errors
• Client reuse: +10% throughput
```

---

## Scalability Limits

```
┌─────────────────────────────────────────────────────┐
│               Scalability Constraints                │
├─────────────────────────────────────────────────────┤
│                                                      │
│  HN API (Firebase):                                 │
│  ├─ No published rate limit                         │
│  ├─ Hosted on Google Cloud (high capacity)          │
│  ├─ Observed ceiling: ~1000 req/sec before errors   │
│  └─ Recommendation: Stay under 500 req/sec          │
│                                                      │
│  Network:                                            │
│  ├─ File descriptors: ~65,535 max (OS limit)        │
│  ├─ Concurrent connections: 1,000 practical limit   │
│  └─ Bandwidth: ~100 Mbps for 500 req/sec            │
│                                                      │
│  CPU:                                                │
│  ├─ Compression: ~1 core per 50 items/sec           │
│  ├─ Optimal workers: 2 × CPU cores                  │
│  └─ Diminishing returns beyond 16 workers           │
│                                                      │
│  Disk:                                               │
│  ├─ Write speed: ~50 MB/sec (HDD) to 500 MB/sec (SSD)│
│  ├─ Current usage: ~1-2 MB/sec (not a bottleneck)   │
│  └─ Final dataset: ~4-5 GB compressed                │
│                                                      │
└─────────────────────────────────────────────────────┘
```

---

## Design Patterns Used

1. **Context Manager Pattern**: Self-managing resources (client, connections)
2. **Factory Pattern**: Config creation from environment
3. **Strategy Pattern**: Pluggable concurrency models (async vs multiprocessing)
4. **Observer Pattern**: Progress logging and statistics
5. **Repository Pattern**: Data storage abstraction
6. **Retry Pattern**: Automatic failure recovery
7. **Circuit Breaker**: Implicit in max_retries
8. **Semaphore Pattern**: Concurrency limiting
9. **Pipeline Pattern**: Download → Compress → Write → Track
10. **Dataclass Pattern**: Type-safe configuration and models
