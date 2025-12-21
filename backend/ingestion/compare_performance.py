#!/usr/bin/env python3
"""
Comparison script to demonstrate the performance difference between
the original ThreadPoolExecutor and the optimized ProcessPoolExecutor + Async I/O.
"""

import subprocess
import time
import sys

def run_ingestion(script_name, workers, limit=100):
    """Run an ingestion script and measure time."""
    
    cmd = [
        "python3",
        script_name,
        "--titles", "Pirkei Avot",
        "--max-workers", str(workers),
        "--limit", str(limit),
        "--no-resume"  # Start fresh for fair comparison
    ]
    
    print(f"Running: {' '.join(cmd)}")
    start_time = time.time()
    
    try:
        result = subprocess.run(
            cmd, 
            check=True, 
            capture_output=True, 
            text=True,
            timeout=300  # 5 minute timeout
        )
        elapsed = time.time() - start_time
        return elapsed, True, result.stdout
    except subprocess.CalledProcessError as e:
        elapsed = time.time() - start_time
        return elapsed, False, e.stderr
    except subprocess.TimeoutExpired:
        return None, False, "Timeout (>5 minutes)"

def main():
    print("=" * 70)
    print("Performance Comparison: Original vs Optimized Ingestion")
    print("=" * 70)
    print()
    print("This will test both versions with the same small book (Pirkei Avot)")
    print("to demonstrate the performance improvement.")
    print()
    
    limit = 100
    
    # Test 1: Original with many threads
    print("\n" + "=" * 70)
    print("TEST 1: Original (ThreadPoolExecutor with 50 threads)")
    print("=" * 70)
    time1, success1, output1 = run_ingestion("main.py", workers=50, limit=limit)
    
    if success1:
        print(f"✓ Completed in {time1:.2f} seconds")
    else:
        print(f"✗ Failed after {time1:.2f} seconds" if time1 else "✗ Timeout")
        print(output1[:500])
    
    # Test 2: Optimized with fewer processes
    print("\n" + "=" * 70)
    print("TEST 2: Optimized (ProcessPoolExecutor + Async with 5 processes)")
    print("=" * 70)
    time2, success2, output2 = run_ingestion("main_optimized.py", workers=5, limit=limit)
    
    if success2:
        print(f"✓ Completed in {time2:.2f} seconds")
    else:
        print(f"✗ Failed after {time2:.2f} seconds" if time2 else "✗ Timeout")
        print(output2[:500])
    
    # Results
    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)
    
    if success1 and success2:
        speedup = time1 / time2
        print(f"\nOriginal (50 threads):     {time1:.2f} seconds")
        print(f"Optimized (5 processes):   {time2:.2f} seconds")
        print(f"\nSpeedup: {speedup:.2f}x faster")
        print(f"Time saved: {time1 - time2:.2f} seconds ({((time1 - time2) / time1 * 100):.1f}%)")
        
        print("\n" + "-" * 70)
        print("Why is it faster?")
        print("-" * 70)
        print("1. True Parallelism: Processes bypass Python's GIL")
        print("2. Concurrent I/O: Each process makes 50 concurrent API calls")
        print("3. Efficient Batching: Fetches all data first, then processes")
        print(f"4. Total Concurrency: 5 processes × 50 connections = 250 concurrent requests")
        print()
        print("With 10 processes, you'd get 500 concurrent requests!")
        
    elif success1:
        print(f"\nOriginal completed in {time1:.2f}s, but optimized version failed.")
        print("Check the error above.")
    elif success2:
        print(f"\nOptimized completed in {time2:.2f}s, but original version failed.")
        print("The optimized version is more robust!")
    else:
        print("\nBoth versions failed. Please check the errors above.")
    
    print("\n" + "=" * 70)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nComparison interrupted by user.")
        sys.exit(130)
