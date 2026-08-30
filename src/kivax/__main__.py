"""`python -m kivax` — the same entry point as the `kivax` console script.

Useful when the script directory isn't on PATH, and it's what the test suite
invokes for its true-subprocess sanity checks.
"""
import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
