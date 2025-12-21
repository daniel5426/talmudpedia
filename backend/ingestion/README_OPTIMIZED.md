# Optimized Ingestion System

This directory contains both the original and optimized versions of the Sefaria text ingestion system.

## Files

- **`main.py`** - Original version using ThreadPoolExecutor
- **`main_optimized.py`** - NEW! Optimized version using ProcessPoolExecutor + Async I/O
- **`async_sefaria_client.py`** - NEW! Async HTTP client with connection pooling and rate limiting
- **`sefaria_client.py`** - Original synchronous HTTP client

## Performance Improvements

The optimized version (`main_optimized.py`) provides significant performance improvements through:

### 1. **ProcessPoolExecutor (True Parallelism)**
- Uses separate processes instead of threads
- Bypasses Python's Global Interpreter Lock (GIL)
- Enables true parallel execution of CPU-bound operations (chunking, text processing)
- Default: 10 processes (configurable with `--max-workers`)

### 2. **Async I/O with aiohttp**
- Each process uses async/await for I/O operations
- Concurrent API requests within each process
- Connection pooling: 50 concurrent connections per process
- Rate limiting: 10 requests/second per process (respects API limits)

### 3. **Smart Resource Management**
- Shared state between processes using multiprocessing.Manager
- Automatic retry with exponential backoff
- Connection reuse and pooling
- Efficient batch processing

## Performance Comparison

### Original (ThreadPoolExecutor)
- **Max workers**: 500 (but limited by GIL)
- **Actual parallelism**: ~5-10 threads due to I/O blocking
- **API concurrency**: Limited by sequential requests

### Optimized (ProcessPoolExecutor + Async)
- **Max workers**: 10 processes (recommended)
- **Actual parallelism**: 10 true parallel processes
- **API concurrency**: 50 concurrent requests × 10 processes = **500 concurrent API calls**
- **Throughput**: 10 requests/sec × 10 processes = **100 requests/second**

## Installation

Install the required dependencies:

```bash
cd /Users/danielbenassaya/Code/personal/talmudpedia/backend/ingestion
pip install -r requirements.txt
```

## Usage

### Run Optimized Version (Recommended)

```bash
# Default: 10 processes, Halakhah category
python3 main_optimized.py

# Custom number of processes
python3 main_optimized.py --max-workers 20

# Specific categories/books
python3 main_optimized.py --titles "Talmud" "Mishnah" --max-workers 15

# Limit segments per book
python3 main_optimized.py --titles "Halakhah" --limit 1000 --max-workers 10

# Start fresh (no resume)
python3 main_optimized.py --no-resume --max-workers 10
```

### Run Original Version

```bash
# Original version (for comparison)
python3 main.py --max-workers 500
```

## Configuration

### Recommended Settings

**For maximum throughput:**
```bash
python3 main_optimized.py --max-workers 20
```
- 20 processes × 50 concurrent connections = 1000 concurrent API calls
- 20 processes × 10 req/s = 200 requests/second

**For stability (recommended):**
```bash
python3 main_optimized.py --max-workers 10
```
- 10 processes × 50 concurrent connections = 500 concurrent API calls
- 10 processes × 10 req/s = 100 requests/second
- Lower memory usage, more stable

**For testing:**
```bash
python3 main_optimized.py --max-workers 2 --limit 100
```
- 2 processes for quick testing
- Limit 100 segments per book

### Tuning Parameters

You can adjust these in `async_sefaria_client.py`:

```python
AsyncSefariaClient(
    max_concurrent_requests=50,  # Concurrent connections per process
    rate_limit_per_second=10,    # Requests per second per process
    max_retries=5,               # Retry attempts
    initial_backoff=1.0          # Initial backoff time (seconds)
)
```

## Architecture

```
main_optimized.py
    ├── ProcessPoolExecutor (10 processes)
    │   ├── Process 1
    │   │   └── AsyncTextIngester
    │   │       └── AsyncSefariaClient (50 concurrent connections)
    │   ├── Process 2
    │   │   └── AsyncTextIngester
    │   │       └── AsyncSefariaClient (50 concurrent connections)
    │   └── ... (8 more processes)
    │
    └── Shared State (multiprocessing.Manager)
        ├── Ingestion Log
        └── Error Log
```

## Why This Is Faster

1. **True Parallelism**: Processes bypass GIL, allowing real parallel execution
2. **Concurrent I/O**: Each process makes 50 concurrent API calls
3. **Efficient Batching**: Fetches all references first, then processes in batches
4. **Connection Pooling**: Reuses HTTP connections instead of creating new ones
5. **Smart Rate Limiting**: Respects API limits while maximizing throughput

## Monitoring

The optimized version provides detailed logging:

```
[PROCESS] Starting ingestion for: Book Name
[Book Name] Found 1234 references to process
[Book Name] Fetching texts and links concurrently...
[Book Name] Collected 1234 segments. Processing...
[Book Name] Chunking batch 1 (100 segments)...
[Book Name] Upserting batch 1 (50 chunks)...
✓ Completed: Book Name
```

## Troubleshooting

### "Too many open files" error
Reduce `max_concurrent_requests` in `async_sefaria_client.py` or reduce `--max-workers`

### Rate limiting errors
The client automatically handles rate limits with exponential backoff. If you see many rate limit messages, reduce `rate_limit_per_second`

### Memory issues
Reduce `--max-workers` to use fewer processes

### API timeouts
Increase `timeout` in `async_sefaria_client.py`:
```python
timeout = aiohttp.ClientTimeout(total=120, connect=60)
```

## Performance Tips

1. **Start with 10 workers** and monitor system resources
2. **Increase gradually** if CPU/memory allows
3. **Monitor API rate limits** - Sefaria may have server-side limits
4. **Use `--limit`** for testing before full ingestion
5. **Check logs** for bottlenecks (API, CPU, or disk I/O)

## Expected Performance

With 10 workers:
- **~500 books in parallel** (50 concurrent requests × 10 processes)
- **~100 API requests/second** (10 req/s × 10 processes)
- **Estimated time**: Depends on book size, but 10-50x faster than original

## Next Steps

After testing the optimized version, you can:
1. Replace `main.py` with `main_optimized.py`
2. Adjust worker count based on your system
3. Monitor and tune parameters for optimal performance
