# SPDX-License-Identifier: MIT
"""Persistent autonomous MCP factory daemon."""

import argparse
import importlib.util
import sys
import time
from pathlib import Path

from factory_runtime import (
    append_jsonl,
    build_factory_journal_entry,
    extract_factory_status,
    extract_repair_applied,
    initial_factory_state,
    read_json,
    should_stop_factory,
    update_factory_state,
    write_json,
)


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _load(script, name):
    spec = importlib.util.spec_from_file_location(name, script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_SCRIPT_DIR = Path(__file__).resolve().parent
_factory_mod = _load(_SCRIPT_DIR / "run_autonomous_factory_cycle.py", "factory_cycle")
run_autonomous_factory_cycle = _factory_mod.run_autonomous_factory_cycle

# Backward-compatible helper aliases for existing tests/internal callers.
_extract_status = extract_factory_status
_extract_repair_applied = extract_repair_applied


def run_factory_daemon(args):
    state_path = Path(args.state_output)
    journal_path = Path(args.journal_output)
    cycle_output = Path(args.cycle_output)

    state = read_json(state_path, initial_factory_state())
    completed_cycles = 0

    while True:
        artifact = {}
        error = None

        try:
            artifact = run_autonomous_factory_cycle(
                portfolio_state=args.portfolio_state,
                ledger=args.ledger,
                capability_ledger=args.capability_ledger_output,
                capability_ledger_output=args.capability_ledger_output,
                policy=args.policy,
                top_k=args.top_k,
                output=str(cycle_output),
            )
        except SystemExit as exc:
            error = exc
            if cycle_output.exists():
                artifact = read_json(cycle_output, {})
            else:
                artifact = {
                    "decision": {"action": "governed_run", "reason": "system_exit"},
                    "cycle_result": {"abort_reason": f"system_exit_{exc.code}"},
                    "status": "failed",
                }
        except Exception as exc:
            error = exc
            if cycle_output.exists():
                artifact = read_json(cycle_output, {})
            else:
                artifact = {
                    "decision": {"action": "governed_run", "reason": "exception"},
                    "cycle_result": {"abort_reason": "exception"},
                    "status": "failed",
                }

        status = extract_factory_status(artifact, error=error)
        state = update_factory_state(state, artifact, status=status)
        write_json(state_path, state)

        journal_entry = build_factory_journal_entry(artifact, status=status, error=error)
        append_jsonl(journal_path, journal_entry)

        print(
            f"factory cycle {state['cycle_count']}: "
            f"decision={state['last_decision']} "
            f"risk={state['last_risk_level']} "
            f"status={state['last_cycle_status']}"
        )

        stop, reason = should_stop_factory(
            state,
            max_failures=args.max_consecutive_failures,
            max_idle_cycles=args.max_consecutive_idle_cycles,
        )
        if stop:
            print(f"factory daemon stopped: {reason}")
            return 1

        completed_cycles += 1
        if args.max_cycles is not None and completed_cycles >= args.max_cycles:
            print("factory daemon stopped: max_cycles_reached")
            return 0

        if args.sleep_seconds <= 0:
            continue
        time.sleep(args.sleep_seconds)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run persistent autonomous MCP factory daemon.")
    parser.add_argument("--portfolio-state", required=True, help="Path to portfolio_state.json.")
    parser.add_argument("--ledger", default=None, help="Path to action_effectiveness_ledger.json.")
    parser.add_argument("--policy", default=None, help="Path to planner_policy.json.")
    parser.add_argument("--top-k", type=int, default=3, help="Planner top-k value.")
    parser.add_argument(
        "--cycle-output",
        default="artifacts/autonomous_factory_cycle.json",
        help="Path to latest factory cycle artifact.",
    )
    parser.add_argument(
        "--state-output",
        default="artifacts/factory_state.json",
        help="Path to persistent daemon state JSON.",
    )
    parser.add_argument(
        "--journal-output",
        default="artifacts/factory_cycle_journal.jsonl",
        help="Path to append-only cycle journal JSONL.",
    )
    parser.add_argument(
        "--max-consecutive-failures",
        type=int,
        default=3,
        help="Stop after this many consecutive failed cycles.",
    )
    parser.add_argument(
        "--max-consecutive-idle-cycles",
        type=int,
        default=5,
        help="Stop after this many consecutive idle cycles.",
    )
    parser.add_argument(
        "--sleep-seconds",
        type=int,
        default=60,
        help="Sleep interval between cycles.",
    )
    parser.add_argument(
        "--max-cycles",
        type=int,
        default=None,
        help="Optional hard cap on cycles for test runs.",
    )
    parser.add_argument(
        "--capability-ledger-output",
        default=None,
        help="Path to persist capability effectiveness ledger across cycles.",
    )

    args = parser.parse_args(argv)
    raise SystemExit(run_factory_daemon(args))


if __name__ == "__main__":
    main()
