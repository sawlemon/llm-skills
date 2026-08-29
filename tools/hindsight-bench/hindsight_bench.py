#!/usr/bin/env python3
"""Launcher so the suite runs from the repository root without installation:

    python3 tools/hindsight-bench/hindsight_bench.py run --mode offline --suite all
"""

import sys
from pathlib import Path

BENCH_ROOT = Path(__file__).resolve().parent
if str(BENCH_ROOT) not in sys.path:
    sys.path.insert(0, str(BENCH_ROOT))

from hindsight_bench.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
