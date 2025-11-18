HN Exporter
===========

**Modern async Python tool for downloading all of HackerNews**

HN publishes all site contents to Google Firebase in real-time, but the API is very slow without clever workarounds (4 items per second with basic requests and there's over 20 million items).

This tool uses modern async/await patterns with httpx to download all of HN concurrently with maximum throughput (15-20x speedup over basic requests).

## ✨ Version 2.0 - Modernized!

This version has been completely rewritten with:
- ⚡ **True async/await** using httpx (not thread-based)
- 🏗️ **Fully encapsulated, self-managing interfaces**
- 📦 **Modern Python packaging** (pyproject.toml, type hints)
- ⚙️ **Configuration management** (environment variables, dataclasses)
- 📝 **Proper logging** (structured, configurable levels)
- 🎯 **Type-safe** throughout (Python 3.10+ with type hints)
- 🔄 **Better error handling** (specific exceptions, retry logic)
- 🧪 **Clean architecture** (separate modules, testable)

Features
--------
- auto-bundle and compress downloaded items
    - Using compression and default bundling options (items stored in batches of 100 then compressed), the current hn dataset size is 3.8 GB (up to item number 21,849,570))
    - all downloaded bundles are given a filesystem time of the last item in the bundle (`ls -latrh cache/`)
- high concurrency options for downloading against the slow API
    - API is hosted at Google so we don't care about rate limits impacting the service
- ability to download individual user data when given a list of usernames
    - hn api doesn't allow enumeration of all users, so you must download all items, then iterate all items to extract each user, then create a list of users to iterate to get their user profile details (TODO: keep a running list of users as items are downloaded)
    - individual user json files are given a filesystem time of their account creation timestamp (`ls -latrh users/`)
- live progress displayed as downloads happen
- auto-resume downloads from most recent archived entry
- example HMM creation scripts
    - `split-to-parts.py` takes everything from the `cache` directory and extracts all contents with record delimiters (warning: uses 30+ GB fully extracted)
    - `markov.py` takes the output of `split-to-parts.py` to generate new text samples given then HN corpus.
    - `markov2.py` does the same but tries to be more clever about parts of speech.


Installation
------------

**Requirements**: Python 3.10+

```bash
# Clone the repository
git clone https://github.com/mattsta/hnexport.git
cd hnexport

# Install dependencies
pip install -r requirements.txt

# Or install in development mode
pip install -e .
```

Usage
-----

### Download all HN items (posts, comments, polls, jobs):

```bash
# Using the CLI
hnexport --items

# With custom concurrency (default: 50)
hnexport --items --concurrent 100

# With multiprocessing for very large downloads
hnexport --items --multiprocess --workers 8

# With custom output directory
hnexport --items --output /data/hn
```

Items will be downloaded into `hn/item/` (or your custom output directory) and each bundle will be filesystem timestamped with a date taken from inside each bundle itself.

### Download user profiles:

```bash
# From a file containing usernames (one per line)
hnexport --users usernames.txt
```

You can use `slow_bulk_usernames.sh` to extract all usernames from all downloaded items to generate the file of usernames to retrieve.

The user JSON files will be filesystem timestamped with the user creation timestamp.

### Environment Variables

You can configure behavior via environment variables:

```bash
# Max concurrent requests (default: 50)
export HNEXPORT_MAX_CONCURRENT=100

# Number of worker processes for multiprocessing (default: auto)
export HNEXPORT_WORKERS=8

# Output directory (default: ./hn)
export HNEXPORT_OUTPUT_DIR=/data/hn

# Logging level (default: INFO)
export HNEXPORT_LOG_LEVEL=DEBUG

# Enable file logging
export HNEXPORT_LOG_FILE=true
export HNEXPORT_LOG_FILE_PATH=hnexport.log
```

### Python API

You can also use hnexport as a library:

```python
import asyncio
from hnexport import HackerNewsClient, HNDownloader

# Async client usage
async def example():
    async with HackerNewsClient() as client:
        # Get highest item ID
        highest = await client.get_highest_item_id()

        # Get a single item
        item = await client.get_item(1)

        # Get multiple items concurrently
        items = await client.get_items_batch([1, 2, 3, 4, 5])

        # Get a user
        user = await client.get_user("pg")

# Download all items
async def download():
    downloader = HNDownloader(output_dir="hn")
    stats = await downloader.download_all_items()
    print(f"Downloaded {stats.successful:,} items in {stats.duration:.1f}s")

asyncio.run(example())
```

### Legacy Scripts

The original scripts are still available for compatibility:
- `import.py` - Original downloader (deprecated, use `hnexport` CLI instead)
- `split-to-parts.py` - Data processor (deprecated, use Python API instead)
- `markov.py` / `markov2.py` - Text generation examples

Architecture
------------

The modernized codebase is organized into clean, well-encapsulated modules:

```
hnexport/
├── __init__.py         # Package exports
├── client.py           # Async HTTP client (httpx-based)
├── config.py           # Configuration management
├── models.py           # Type-safe data models
├── exceptions.py       # Custom exception types
├── logger.py           # Logging configuration
├── downloader.py       # Download orchestration
├── processor.py        # Bundle processing
└── cli.py              # Command-line interface
```

### Key Improvements

**Before (v1)**: Thread-based concurrency with `requests-futures`
```python
# Old approach - thread pools, not true async
session = FuturesSession(max_workers=25)
futures = [session.get(url) for url in urls]
results = [f.result() for f in futures]
```

**After (v2)**: True async/await with `httpx`
```python
# New approach - native async/await
async with HackerNewsClient() as client:
    items = await client.get_items_batch(item_ids)
```

### Benefits

1. **Better Resource Efficiency**: Async I/O uses far less memory than thread pools
2. **Self-Managing**: Client handles connection pooling, retries, and cleanup automatically
3. **Type Safety**: Full type hints enable better IDE support and catch errors early
4. **Configurable**: Environment variables and dataclasses replace hard-coded constants
5. **Testable**: Clean separation of concerns makes unit testing straightforward
6. **Modern**: Uses current Python best practices (3.10+, async/await, context managers)

Limitations
-----------
HN allows modification of many items (user profiles, recent edits to posts) but has no historical change API. The only way to get changed items is to redownload items. So, if you want to get all _current_ user profiles, you have to download all user profiles every time you want them to be up-to-date. Also, once you download an item bundle, the live contents can change (or be entirely deleted) after you download it, so for a complete long-term site sync, you should always delete your last two days of bundles then re-download them after all edit capability timers have expired.

Also, because the HN API can't enumerate users, we can only discover users who have posted or commented on the site. If a user registers and never posts or comments, we have no way of discovering them in the API.


Contributions
-------------
Feel free to improve features, fix errors, or implement missing functionality (username saving/appending as new item downloads happen, etc). Contributions welcome.

If you want to provide any datasets or write more in-depth tutorials about using `hnexport`, open an issue with links to your results/writings and we'll add them to this readme.
