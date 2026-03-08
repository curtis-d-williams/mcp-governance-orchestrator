#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Aggregate run envelopes into tier3_multi_run_aggregate.json.

Reads tier3_run_envelope.json (written by run_portfolio_task.py in multi-task
mode) and writes tier3_multi_run_aggregate.json.  Idempotent and fail-safe:
when the envelope file is absent this script exits cleanly.
"""

import json
import sys
from pathlib import Path

ENVELOPE_FILE = Path("tier3_run_envelope.json")
AGGREGATE_FILE = Path("tier3_multi_run_aggregate.json")


def main() -> int:
    if not ENVELOPE_FILE.exists():
        print(f"No envelope at {ENVELOPE_FILE}; skipping aggregation.")
        return 0
    try:
        data = json.loads(ENVELOPE_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"error: failed to read envelope: {exc}", file=sys.stderr)
        return 1
    AGGREGATE_FILE.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"Aggregated {len(data)} entries to {AGGREGATE_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
