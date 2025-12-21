# Migration Guide: From Old to Optimized Ingestion

## Overview
This guide helps you migrate from `main.py` (ThreadPoolExecutor) to `main_optimized.py` (ProcessPoolExecutor + Async I/O).

## Pre-Migration Checklist

- [ ] Install `aiohttp`: `pip install aiohttp`
- [ ] Backup your ingestion logs: `cp ingestion_log.json ingestion_log.json.backup`
- [ ] Backup your error logs: `cp ingestion_errors.json ingestion_errors.json.backup`
- [ ] Test with small dataset first

## Step-by-Step Migration

### Step 1: Test the Optimized Version

Start with a small test to verify everything works:

```bash
python3 test_optimized.py
```

This will:
- Test with a small book (Pirkei Avot)
- Use only 2 processes
- Limit to 50 segments
- Verify the system works correctly

**Expected output:**
```
Testing Optimized Ingestion System
Test Configuration:
  Book: Pirkei Avot
  Max Workers: 2
  Segment Limit: 50
...
✓ Test completed successfully!
```

### Step 2: Compare Performance (Optional)

Run a side-by-side comparison:

```bash
python3 compare_performance.py
```

This will show you the actual speedup on your system.

### Step 3: Run Parallel Test

Test with your actual workload but limited segments:

```bash
# Test with your categories but limited segments
python3 main_optimized.py --titles "Halakhah" --max-workers 5 --limit 100
```

Monitor:
- CPU usage (should be high)
- Memory usage (should be stable)
- No errors in output

### Step 4: Full Migration

Once testing is successful, run the full ingestion:

```bash
# Recommended: 10 processes
python3 main_optimized.py --titles "Halakhah" --max-workers 10

# Or with your specific categories
python3 main_optimized.py --titles "Talmud" "Mishnah" "Halakhah" --max-workers 10
```

### Step 5: Monitor Progress

Watch for:
- ✓ Completed messages for each book
- No repeated rate limit errors
- Steady progress through books
- CPU usage near 100%

## Command Comparison

### Old Command
```bash
python3 main.py --titles "Halakhah" --max-workers 500
```

### New Command (Equivalent Performance)
```bash
python3 main_optimized.py --titles "Halakhah" --max-workers 10
```

### New Command (Better Performance)
```bash
python3 main_optimized.py --titles "Halakhah" --max-workers 20
```

## Configuration Changes

### Old (main.py)
```python
ThreadPoolExecutor(max_workers=500)
└── SefariaClient (requests)
    └── ~10 concurrent connections
```

### New (main_optimized.py)
```python
ProcessPoolExecutor(max_workers=10)
└── AsyncSefariaClient (aiohttp)
    ├── 50 concurrent connections per process
    └── 10 requests/second per process
```

## Tuning Guide

### Conservative (Safe Start)
```bash
python3 main_optimized.py --max-workers 5
```
- 5 processes × 50 connections = 250 concurrent
- 5 processes × 10 req/s = 50 requests/second
- Lower resource usage

### Recommended (Balanced)
```bash
python3 main_optimized.py --max-workers 10
```
- 10 processes × 50 connections = 500 concurrent
- 10 processes × 10 req/s = 100 requests/second
- Good balance of speed and stability

### Aggressive (Maximum Speed)
```bash
python3 main_optimized.py --max-workers 20
```
- 20 processes × 50 connections = 1000 concurrent
- 20 processes × 10 req/s = 200 requests/second
- Requires good system resources

### Custom Tuning

Edit `async_sefaria_client.py` to adjust per-process limits:

```python
AsyncSefariaClient(
    max_concurrent_requests=50,  # Adjust based on memory
    rate_limit_per_second=10,    # Adjust based on API limits
    max_retries=5,               # Increase if seeing failures
    initial_backoff=1.0          # Increase if rate limited
)
```

## Troubleshooting Migration Issues

### Issue: "Too many open files"

**Solution 1:** Reduce concurrent connections
```python
# In async_sefaria_client.py
max_concurrent_requests=25  # Reduced from 50
```

**Solution 2:** Reduce processes
```bash
python3 main_optimized.py --max-workers 5
```

**Solution 3:** Increase system limits (macOS)
```bash
ulimit -n 4096
```

### Issue: Rate limiting errors (429)

**Solution:** Reduce rate limit
```python
# In async_sefaria_client.py
rate_limit_per_second=5  # Reduced from 10
```

### Issue: Memory usage too high

**Solution:** Reduce workers
```bash
python3 main_optimized.py --max-workers 5
```

### Issue: Import errors

**Solution:** Install dependencies
```bash
pip install aiohttp
```

### Issue: Slower than expected

**Check:**
1. CPU usage - should be near 100%
2. Network usage - should be high
3. Logs for rate limiting or errors
4. System resources (RAM, disk I/O)

**Solutions:**
- Increase `max_workers` if CPU < 80%
- Check network bandwidth
- Verify no rate limiting in logs

## Rollback Plan

If you need to rollback to the old system:

```bash
# Use the original main.py
python3 main.py --titles "Halakhah" --max-workers 50

# Restore backups if needed
cp ingestion_log.json.backup ingestion_log.json
cp ingestion_errors.json.backup ingestion_errors.json
```

## Performance Expectations

### Before (main.py with 500 threads)
- Actual concurrency: ~10 operations
- Speed: Baseline (1x)
- Memory: High

### After (main_optimized.py with 10 processes)
- Actual concurrency: 500 operations
- Speed: **10-20x faster**
- Memory: Moderate

### After (main_optimized.py with 20 processes)
- Actual concurrency: 1000 operations
- Speed: **20-40x faster**
- Memory: High

## Monitoring Commands

### Watch CPU usage
```bash
top -pid $(pgrep -f main_optimized.py)
```

### Watch memory usage
```bash
ps aux | grep main_optimized.py
```

### Count active processes
```bash
pgrep -f main_optimized.py | wc -l
```

### Monitor log file
```bash
tail -f ingestion_log.json
```

## Success Criteria

Migration is successful when:
- ✅ All tests pass
- ✅ Books are processing in parallel
- ✅ CPU usage is high (80-100%)
- ✅ No repeated errors in logs
- ✅ Significantly faster than old system
- ✅ Memory usage is stable

## Post-Migration

After successful migration:

1. **Update your scripts** to use `main_optimized.py`
2. **Document your optimal settings** (workers, limits)
3. **Set up monitoring** for long-running ingestions
4. **Consider replacing** `main.py` with `main_optimized.py`

## Questions?

Check these files:
- `OPTIMIZATION_SUMMARY.md` - Quick reference
- `WHY_IT_WASNT_PARALLEL.md` - Detailed explanation
- `README_OPTIMIZED.md` - Complete documentation
- `show_architecture.py` - Visual comparison

## Final Recommendation

**Start conservative, scale up:**

```bash
# Day 1: Test
python3 test_optimized.py

# Day 2: Small workload
python3 main_optimized.py --max-workers 5 --limit 1000

# Day 3: Medium workload
python3 main_optimized.py --max-workers 10

# Day 4+: Full production
python3 main_optimized.py --max-workers 10  # or 20 if system handles it
```

This gradual approach ensures stability while maximizing performance.
