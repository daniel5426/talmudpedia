#!/usr/bin/env python3
"""
Quick test script for the optimized ingestion system.
Tests with a small book to verify everything works.
"""

import subprocess
import sys

def test_optimized_ingestion():
    """Test the optimized ingestion with a small book."""
    
    print("=" * 60)
    print("Testing Optimized Ingestion System")
    print("=" * 60)
    print()
    
    # Test with a small book and limited segments
    test_book = "Pirkei Avot"  # Small Mishnah tractate
    max_workers = 2
    limit = 50
    
    print(f"Test Configuration:")
    print(f"  Book: {test_book}")
    print(f"  Max Workers: {max_workers}")
    print(f"  Segment Limit: {limit}")
    print()
    
    cmd = [
        "python3",
        "main_optimized.py",
        "--titles", test_book,
        "--max-workers", str(max_workers),
        "--limit", str(limit)
    ]
    
    print(f"Running command: {' '.join(cmd)}")
    print()
    print("-" * 60)
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=False, text=True)
        print("-" * 60)
        print()
        print("✓ Test completed successfully!")
        print()
        print("The optimized version is working correctly.")
        print("You can now run it with more workers and books:")
        print()
        print("  python3 main_optimized.py --titles 'Halakhah' --max-workers 10")
        print()
        return 0
    except subprocess.CalledProcessError as e:
        print("-" * 60)
        print()
        print("✗ Test failed!")
        print(f"Error: {e}")
        print()
        print("Please check the error messages above.")
        return 1
    except KeyboardInterrupt:
        print()
        print("Test interrupted by user.")
        return 130

if __name__ == "__main__":
    sys.exit(test_optimized_ingestion())
