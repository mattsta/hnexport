# API Reference

Complete reference for HNexport's Python API.

---

## Module: `hnexport`

### Main Exports

```python
from hnexport import (
    # Client
    HackerNewsClient,

    # Downloader
    HNDownloader,
    download_with_multiprocessing,

    # Configuration
    Config,
    config,

    # Models
    HNItem,
    HNUser,
    DownloadStats,

    # Exceptions
    HNExportError,
    APIError,
    NetworkError,
    ItemNotFoundError,
    StorageError,

    # Logging
    logger,
    setup_logger,
)
```

---

## Classes

### `HackerNewsClient`

Async HTTP client for HackerNews Firebase API.

#### Constructor

```python
HackerNewsClient(
    max_concurrent: Optional[int] = None,
    max_retries: Optional[int] = None,
    timeout: Optional[tuple[float, float]] = None,
)
```

**Parameters:**
- `max_concurrent` (int, optional): Maximum concurrent requests. Default: 50 (from config)
- `max_retries` (int, optional): Maximum retry attempts. Default: 7
- `timeout` (tuple[float, float], optional): (connect_timeout, read_timeout). Default: (5.0, 10.0)

**Usage:**
```python
async with HackerNewsClient(max_concurrent=100) as client:
    item = await client.get_item(1)
```

#### Methods

##### `get_item(item_id: int) -> Optional[HNItem]`

Fetch a single item by ID.

**Parameters:**
- `item_id` (int): HackerNews item ID

**Returns:**
- `HNItem` if found
- `None` if item is deleted or doesn't exist

**Raises:**
- `APIError`: On API errors
- `NetworkError`: On network errors
- `RetryExhaustedError`: If all retries fail

**Example:**
```python
async with HackerNewsClient() as client:
    item = await client.get_item(1)
    if item:
        print(f"{item.title} by {item.by}")
```

---

##### `get_items_batch(item_ids: list[int]) -> list[Optional[HNItem]]`

Fetch multiple items concurrently.

**Parameters:**
- `item_ids` (list[int]): List of item IDs to fetch

**Returns:**
- `list[Optional[HNItem]]`: List of items (None for deleted/errors)

**Example:**
```python
async with HackerNewsClient() as client:
    items = await client.get_items_batch([1, 2, 3, 4, 5])
    valid_items = [i for i in items if i is not None]
```

---

##### `get_user(username: str) -> Optional[HNUser]`

Fetch a user profile.

**Parameters:**
- `username` (str): HackerNews username

**Returns:**
- `HNUser` if found
- `None` if user doesn't exist

**Example:**
```python
async with HackerNewsClient() as client:
    user = await client.get_user("pg")
    print(f"Karma: {user.karma}")
```

---

##### `get_highest_item_id() -> int`

Fetch the highest item ID from HackerNews.

**Returns:**
- `int`: The highest item ID currently available

**Example:**
```python
async with HackerNewsClient() as client:
    highest = await client.get_highest_item_id()
    print(f"Latest item: {highest}")
```

---

##### `get_raw_items_batch(item_ids: list[int]) -> list[bytes]`

Fetch multiple items as raw JSON bytes (for bundling).

**Parameters:**
- `item_ids` (list[int]): List of item IDs

**Returns:**
- `list[bytes]`: Raw JSON response bytes (including b'null' for deleted items)

**Example:**
```python
async with HackerNewsClient() as client:
    raw_data = await client.get_raw_items_batch([1, 2, 3])
    # raw_data = [b'{"id":1,...}', b'{"id":2,...}', b'null']
```

---

### `HNDownloader`

High-performance async downloader for HackerNews content.

#### Constructor

```python
HNDownloader(
    output_dir: Optional[Path] = None,
    bundle_size: Optional[int] = None,
)
```

**Parameters:**
- `output_dir` (Path, optional): Output directory for downloaded data. Default: `hn/`
- `bundle_size` (int, optional): Items per compressed bundle. Default: 100

**Example:**
```python
from pathlib import Path

downloader = HNDownloader(
    output_dir=Path("/data/hn"),
    bundle_size=100
)
```

#### Methods

##### `download_all_items() -> DownloadStats`

Download all HackerNews items.

**Returns:**
- `DownloadStats`: Download statistics

**Example:**
```python
downloader = HNDownloader()
stats = await downloader.download_all_items()
print(f"Downloaded {stats.successful:,} items in {stats.duration:.1f}s")
```

---

##### `download_item_range(start_id: int, end_id: int, item_type: str = "item", client: Optional[HackerNewsClient] = None) -> None`

Download a range of items with bundling.

**Parameters:**
- `start_id` (int): First item ID
- `end_id` (int): Last item ID (inclusive)
- `item_type` (str, optional): Type directory name. Default: "item"
- `client` (HackerNewsClient, optional): Existing client to reuse

**Example:**
```python
# Download specific range
await downloader.download_item_range(0, 999)

# With custom client
async with HackerNewsClient(max_concurrent=200) as client:
    await downloader.download_item_range(0, 999, client=client)
```

---

##### `download_users_from_file(users_file: Path) -> DownloadStats`

Download user profiles from a file containing usernames.

**Parameters:**
- `users_file` (Path): Path to file with one username per line

**Returns:**
- `DownloadStats`: Download statistics

**Example:**
```python
from pathlib import Path

stats = await downloader.download_users_from_file(
    Path("usernames.txt")
)
```

---

### Data Models

#### `HNItem`

Represents a HackerNews item (story, comment, job, poll, or pollopt).

**Attributes:**
```python
@dataclass
class HNItem:
    id: int
    type: Literal["story", "comment", "job", "poll", "pollopt"]
    by: Optional[str] = None          # Author username
    time: Optional[int] = None         # Unix timestamp
    text: Optional[str] = None         # Comment/poll text (HTML)
    dead: Optional[bool] = None        # Item is dead
    deleted: Optional[bool] = None     # Item is deleted
    parent: Optional[int] = None       # Parent item ID
    poll: Optional[int] = None         # Poll ID (for pollopts)
    kids: Optional[list[int]] = None   # Child comment IDs
    url: Optional[str] = None          # Story URL
    score: Optional[int] = None        # Story/poll score
    title: Optional[str] = None        # Story/poll title
    parts: Optional[list[int]] = None  # Poll's related pollopts
    descendants: Optional[int] = None  # Total comment count
```

**Properties:**
- `is_deleted -> bool`: Check if item is deleted or dead

**Methods:**
- `to_dict() -> dict`: Convert to dictionary (excluding None values)

**Example:**
```python
item = await client.get_item(1)
if item:
    print(f"Title: {item.title}")
    print(f"Type: {item.type}")
    print(f"Deleted: {item.is_deleted}")
    print(f"Dict: {item.to_dict()}")
```

---

#### `HNUser`

Represents a HackerNews user profile.

**Attributes:**
```python
@dataclass
class HNUser:
    id: str                           # Username
    created: int                      # Unix timestamp
    karma: int                        # User's karma score
    about: Optional[str] = None       # Self-description (HTML)
    submitted: Optional[list[int]] = None  # Submitted item IDs
```

**Methods:**
- `to_dict() -> dict`: Convert to dictionary (excluding None values)

**Example:**
```python
user = await client.get_user("pg")
if user:
    print(f"Username: {user.id}")
    print(f"Karma: {user.karma}")
    print(f"Submissions: {len(user.submitted or [])}")
```

---

#### `DownloadStats`

Statistics for a download session.

**Attributes:**
```python
@dataclass
class DownloadStats:
    total_items: int = 0
    successful: int = 0
    failed: int = 0
    null_responses: int = 0
    bundles_created: int = 0
    start_time: float = 0.0
    end_time: float = 0.0
```

**Properties:**
- `duration -> float`: Download duration in seconds
- `items_per_second -> float`: Download rate

**Example:**
```python
stats = await downloader.download_all_items()
print(f"Duration: {stats.duration:.1f}s")
print(f"Rate: {stats.items_per_second:.1f} items/sec")
print(f"Success: {stats.successful:,}/{stats.total_items:,}")
```

---

## Functions

### `download_with_multiprocessing(start_id: int, end_id: int, num_workers: Optional[int] = None) -> None`

Download items using multiprocessing for CPU-bound work distribution.

**Parameters:**
- `start_id` (int): First item ID
- `end_id` (int): Last item ID
- `num_workers` (int, optional): Number of worker processes. Default: CPU count

**Example:**
```python
# Download using 8 worker processes
await download_with_multiprocessing(0, 1000000, num_workers=8)
```

---

## Configuration

### `Config`

Main configuration container (dataclass).

**Attributes:**
```python
@dataclass
class Config:
    api: APIConfig
    concurrency: ConcurrencyConfig
    storage: StorageConfig
    logging: LoggingConfig
```

**Class Methods:**
- `from_env() -> Config`: Create configuration from environment variables

**Example:**
```python
from hnexport import config

# Access configuration
print(config.concurrency.max_concurrent_requests)
print(config.storage.output_dir)

# Modify at runtime
config.concurrency.max_concurrent_requests = 100

# Create custom config
custom_config = Config.from_env()
```

---

### `APIConfig`

Configuration for HackerNews API access.

**Attributes:**
```python
base_url: str = "https://hacker-news.firebaseio.com/v0"
connect_timeout: float = 5.0
read_timeout: float = 10.0
max_retries: int = 7
backoff_factor: float = 0.5
```

**Properties:**
- `timeout -> tuple[float, float]`: Returns (connect, read) tuple

---

### `ConcurrencyConfig`

Configuration for concurrent operations.

**Attributes:**
```python
max_concurrent_requests: int = 50  # HNEXPORT_MAX_CONCURRENT
multiprocessing_workers: Optional[int] = None  # HNEXPORT_WORKERS
items_per_worker: int = 20_000
batch_size: int = 100
pipeline_groups: int = 10
```

---

### `StorageConfig`

Configuration for data storage.

**Attributes:**
```python
output_dir: Path = Path("hn")  # HNEXPORT_OUTPUT_DIR
bundle_size: int = 100
compression_preset: int = 9  # lzma level (0-9)
monthly_split_duration: int = 3  # months
```

---

### `LoggingConfig`

Configuration for logging.

**Attributes:**
```python
level: str = "INFO"  # HNEXPORT_LOG_LEVEL
format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
log_to_file: bool = False  # HNEXPORT_LOG_FILE=true
log_file: Optional[Path] = None  # HNEXPORT_LOG_FILE_PATH
```

---

## Exceptions

### Exception Hierarchy

```
HNExportError (Base)
├── APIError
│   ├── RateLimitError
│   └── ItemNotFoundError
├── NetworkError
│   └── RetryExhaustedError
├── StorageError
└── ConfigurationError
```

### `HNExportError`

Base exception for all HNexport errors.

---

### `APIError`

Error communicating with HackerNews API.

**Example:**
```python
try:
    item = await client.get_item(1)
except APIError as e:
    print(f"API error: {e}")
```

---

### `ItemNotFoundError`

Requested item does not exist (404).

---

### `NetworkError`

Network-related error during download.

---

### `RetryExhaustedError`

All retry attempts have been exhausted.

**Attributes:**
- `attempts` (int): Number of retry attempts made
- `last_error` (Exception): The last error encountered

**Example:**
```python
try:
    item = await client.get_item(1)
except RetryExhaustedError as e:
    print(f"Failed after {e.attempts} attempts")
    print(f"Last error: {e.last_error}")
```

---

## Logging

### `setup_logger(name: str = "hnexport", level: Optional[str] = None) -> logging.Logger`

Set up and configure a logger.

**Parameters:**
- `name` (str): Logger name
- `level` (str, optional): Log level. Default: from config

**Returns:**
- `logging.Logger`: Configured logger instance

**Example:**
```python
from hnexport import setup_logger

# Create custom logger
my_logger = setup_logger("my_app", level="DEBUG")
my_logger.info("Hello, world!")
```

---

### `logger`

Default logger instance.

**Example:**
```python
from hnexport import logger

logger.info("Starting download")
logger.debug("Debug information")
logger.error("Error occurred", exc_info=True)
```

---

## Environment Variables

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `HNEXPORT_MAX_CONCURRENT` | int | 50 | Maximum concurrent requests |
| `HNEXPORT_WORKERS` | int | auto | Number of worker processes |
| `HNEXPORT_OUTPUT_DIR` | Path | hn | Output directory |
| `HNEXPORT_LOG_LEVEL` | str | INFO | Logging level (DEBUG/INFO/WARNING/ERROR) |
| `HNEXPORT_LOG_FILE` | bool | false | Enable file logging |
| `HNEXPORT_LOG_FILE_PATH` | Path | hnexport.log | Log file path |

**Example:**
```bash
export HNEXPORT_MAX_CONCURRENT=100
export HNEXPORT_LOG_LEVEL=DEBUG
python3 my_script.py
```

---

## Type Hints

All functions and methods include comprehensive type hints:

```python
async def get_item(self, item_id: int) -> Optional[HNItem]: ...
async def get_items_batch(self, item_ids: list[int]) -> list[Optional[HNItem]]: ...
def download_all_items(self) -> DownloadStats: ...
```

Use with type checkers:
```bash
mypy my_script.py
```

---

## Complete Example

```python
import asyncio
from pathlib import Path
from hnexport import (
    HackerNewsClient,
    HNDownloader,
    config,
    logger,
    setup_logger,
)

async def main():
    # Configure
    setup_logger(level="INFO")
    config.concurrency.max_concurrent_requests = 100

    # Download items
    downloader = HNDownloader(output_dir=Path("data/hn"))

    # Method 1: Download all items
    stats = await downloader.download_all_items()
    logger.info(f"Downloaded {stats.successful:,} items")

    # Method 2: Custom range with custom client
    async with HackerNewsClient(max_concurrent=200) as client:
        # Get specific items
        items = await client.get_items_batch([1, 2, 3])

        # Filter stories
        stories = [i for i in items if i and i.type == "story"]

        for story in stories:
            logger.info(f"{story.title} by {story.by}")

        # Download range
        await downloader.download_item_range(
            1000, 2000,
            client=client
        )

    # Method 3: Download users
    stats = await downloader.download_users_from_file(
        Path("usernames.txt")
    )
    logger.info(f"Downloaded {stats.successful} users")

if __name__ == "__main__":
    asyncio.run(main())
```
