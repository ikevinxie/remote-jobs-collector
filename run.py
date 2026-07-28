#!/usr/bin/env python3
"""便捷入口:python3 run.py run / python3 run.py report"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from remote_jobs.__main__ import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
