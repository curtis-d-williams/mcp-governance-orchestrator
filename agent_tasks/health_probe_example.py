"""
Deterministic agent task: emit known degraded health signals for example pipeline validation.

Returns a fixed signal payload that exercises the Phase A → Phase B → Phase C pipeline:
  - recent_failures: 2  → triggers rerun_failed_task action in build_portfolio_state_from_artifacts.py
  - stale_runs: 0
  - determinism_ok: true

This task is intentionally example-only.  It does not inspect the real repo state;
it exists solely so that the example operational path produces at least one eligible
action and the governed planner loop can execute without --force.

stdlib-only, no external dependencies, no file outputs — result is returned in memory.
"""

from collections import OrderedDict


TASK_NAME = "health_probe_example"

# Fixed degraded signal values for example pipeline validation.
_RECENT_FAILURES = 2   # triggers rerun_failed_task action (threshold: >= 2)
_STALE_RUNS = 0
_DETERMINISM_OK = True


def run():
    """Return a fixed degraded health signal payload.

    Returns:
        OrderedDict with deterministic keys:
          task_name, recent_failures, stale_runs, determinism_ok
    """
    return OrderedDict([
        ("task_name", TASK_NAME),
        ("recent_failures", _RECENT_FAILURES),
        ("stale_runs", _STALE_RUNS),
        ("determinism_ok", _DETERMINISM_OK),
    ])
