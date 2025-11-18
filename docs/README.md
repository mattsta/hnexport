# HNexport Documentation

Comprehensive documentation for HNexport v2.0 - Modern async HackerNews downloader.

## Documentation Index

### Getting Started
- **[../README.md](../README.md)** - Quick start guide and basic usage
- **[MIGRATION.md](MIGRATION.md)** - Upgrading from v1.0 to v2.0

### Reference Documentation
- **[API_REFERENCE.md](API_REFERENCE.md)** - Complete Python API documentation
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - System architecture and design
- **[USE_CASES.md](USE_CASES.md)** - Practical examples and use cases

### Analysis & Decisions
- **[BENEFITS_DRAWBACKS.md](BENEFITS_DRAWBACKS.md)** - Detailed pros/cons analysis
- **[../REVIEW.md](../REVIEW.md)** - Code review and performance analysis

## Quick Navigation

### For Users
1. New to HNexport? Start with [README.md](../README.md)
2. Migrating from v1.0? Read [MIGRATION.md](MIGRATION.md)
3. Need examples? Check [USE_CASES.md](USE_CASES.md)

### For Developers
1. Understanding the system? See [ARCHITECTURE.md](ARCHITECTURE.md)
2. Using the Python API? Check [API_REFERENCE.md](API_REFERENCE.md)
3. Making decisions? Review [BENEFITS_DRAWBACKS.md](BENEFITS_DRAWBACKS.md)

### For DevOps
1. Production deployment? See [USE_CASES.md#production-deployments](USE_CASES.md#production-deployments)
2. Performance tuning? Check [ARCHITECTURE.md#performance-characteristics](ARCHITECTURE.md#performance-characteristics)
3. Troubleshooting? See [USE_CASES.md#troubleshooting](USE_CASES.md#troubleshooting)

## Documentation Structure

```
docs/
├── README.md                    # This file
├── API_REFERENCE.md            # Complete API docs
│   ├── Classes (HackerNewsClient, HNDownloader)
│   ├── Data Models (HNItem, HNUser, DownloadStats)
│   ├── Configuration (Config, environment variables)
│   └── Exceptions (error hierarchy)
│
├── ARCHITECTURE.md             # System design
│   ├── Component diagrams
│   ├── Data flow
│   ├── Concurrency models
│   ├── Performance analysis
│   └── Design patterns
│
├── USE_CASES.md               # Practical examples
│   ├── Basic usage
│   ├── Advanced patterns
│   ├── Data analysis
│   ├── Production deployments
│   ├── Research applications
│   └── Troubleshooting
│
├── MIGRATION.md               # v1 → v2 upgrade
│   ├── Breaking changes
│   ├── Step-by-step migration
│   ├── Configuration mapping
│   └── Rollback plan
│
└── BENEFITS_DRAWBACKS.md      # Analysis
    ├── Performance benefits
    ├── Architecture benefits
    ├── Limitations
    ├── Trade-offs
    └── Recommendations
```

## Key Features

### Self-Managing Interfaces
```python
# Resources automatically managed
async with HackerNewsClient() as client:
    items = await client.get_items_batch([1, 2, 3])
# Client automatically closed, connections released
```

### Type-Safe Throughout
```python
# Full type hints enable IDE support
async def get_item(self, item_id: int) -> Optional[HNItem]:
    ...
```

### Configurable via Environment
```bash
export HNEXPORT_MAX_CONCURRENT=100
export HNEXPORT_OUTPUT_DIR=/data/hn
hnexport --items
```

## Performance Summary

| Metric | Value |
|--------|-------|
| **Throughput** | 100-600 items/sec |
| **Memory** | ~65 MB (single process) |
| **Concurrency** | 50 async requests (default) |
| **Scalability** | Near-linear with multiprocessing |
| **Speed vs v1.0** | 30-50% faster (single), 7x faster (multi) |

## Support

- **Issues**: Report bugs on GitHub
- **Questions**: Check USE_CASES.md for examples
- **Contributions**: See ../README.md for guidelines

## Version

**Current**: v2.0.0  
**Python**: 3.10+  
**Updated**: January 2025
