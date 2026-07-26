"""
Standalone entry point for the live runner, made specifically so launchd
(or any other process manager that doesn't reliably apply PYTHONPATH/cwd
the same way an interactive shell does) can run this reliably.

Run directly with an absolute path, no -m, no PYTHONPATH needed:
  /usr/bin/python3 /path/to/helios/run_live_runner.py
"""
import sys
import os

# Guarantee the project root is importable regardless of how/where this
# script gets invoked from.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine.live_runner import run_forever

if __name__ == "__main__":
    run_forever()
