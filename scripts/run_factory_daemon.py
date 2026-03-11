# SPDX-License-Identifier: MIT
"""Persistent autonomous MCP factory daemon."""

import argparse
import importlib.util
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


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


def _utcnow_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_json(path, default):
    p = Path(path)
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def _write_json(path, payload):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _append_jsonl(path, payload):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, sort_keys=True) + "\n")


def _initial_state():
    return {
        "cycle_count": 0,
        "last_cycle_status": None,
        "last_decision": None,
        "last_risk_level": None,
        "last_learning_applied": False,
        "consecutive_idle_cycles": 0,
        "consecutive_failed_cycles": 0,
        "last_updated_at": None,
    }


def _extract_risk_level(artifact):
    evaluation = artifact.get("evaluation") or {}
    if evaluation.get("risk_level"):
        return evaluation["risk_level"]

    cycle_result = artifact.get("cycle_result") or {}
    if cycle_result.get("risk_level"):
        return cycle_result["risk_level"]

    baseline = cycle_result.get("baseline_evaluation") or {}
    if baseline.get("risk_level"):
        return baseline["risk_level"]

    repaired = cycle_result.get("repaired_evaluation") or {}
    if repaired.get("risk_level"):
        return repaired["risk_level"]

    return None


def _extract_learning_applied(artifact):
    learning = artifact.get("learning_update") or {}
    if learning.get("applied") is True:
        return True

    cycle_result = artifact.get("cycle_result") or {}
    nested = cycle_result.get("learning_update") or {}
    return nested.get("applied") is True


def _extract_repair_applied(artifact):
    cycle_result = artifact.get("cycle_result") or {}

    if cycle_result.get("auto_repair_applied") is True:
        return True

    if cycle_result.get("repair_success") is True:
        return True

    repair_cycle = cycle_result.get("auto_repair_cycle") or {}
    return repair_cycle.get("repair_success") is True


def _reasons_indicate_idle(reasons):
    normalized = " | ".join(str(r).lower() for r in (reasons or []))
    return (
        "no actions" in normalized
        or "planner produced no actions" in normalized
        or "empty" in normalized
        or "no action window" in normalized
    )


def _extract_status(artifact, error=None):
    if error is not None:
        return "failed"

    decision = (artifact.get("decision") or {}).get("action")
    if decision == "idle":
        return "idle"

    evaluation = artifact.get("evaluation") or {}
    cycle_result = artifact.get("cycle_result") or {}

    if cycle_result.get("idle") is True:
        return "idle"

    if cycle_result.get("abort_reason"):
        return "failed"

    if _reasons_indicate_idle(evaluation.get("reasons")):
        return "idle"

    baseline = cycle_result.get("baseline_evaluation") or {}
    if _reasons_indicate_idle(baseline.get("reasons")):
        return "idle"

    if decision == "repair_only":
        if cycle_result.get("repair_success") is True:
            return "completed"
        return "failed"

    return artifact.get("status") or "completed"


def _build_journal_entry(artifact, *, status, error=None):
    cycle_result = artifact.get("cycle_result") or {}
    decision = artifact.get("decision") or {}
    return {
        "timestamp": _utcnow_iso(),
        "decision": decision.get("action"),
        "risk_level": _extract_risk_level(artifact),
        "repair_applied": _extract_repair_applied(artifact),
        "learning_applied": _extract_learning_applied(artifact),
        "status": status,
        "error": str(error) if error else None,
        "repair_cycle_status": cycle_result.get("repair_cycle_status")
        or cycle_result.get("status"),
    }


def _update_state(state, artifact, *, status):
    next_state = dict(state)
    next_state["cycle_count"] = int(state.get("cycle_count", 0)) + 1
    next_state["last_cycle_status"] = status
    next_state["last_decision"] = (artifact.get("decision") or {}).get("action")
    next_state["last_risk_level"] = _extract_risk_level(artifact)
    next_state["last_learning_applied"] = _extract_learning_applied(artifact)

    if status == "idle":
        next_state["consecutive_idle_cycles"] = int(state.get("consecutive_idle_cycles", 0)) + 1
    else:
        next_state["consecutive_idle_cycles"] = 0

    if status == "failed":
        next_state["consecutive_failed_cycles"] = int(state.get("consecutive_failed_cycles", 0)) + 1
    else:
        next_state["consecutive_failed_cycles"] = 0

    next_state["last_updated_at"] = _utcnow_iso()
    return next_state


def _should_stop(state, *, max_failures, max_idle_cycles):
    if int(state.get("consecutive_failed_cycles", 0)) >= max_failures:
        return True, "max_consecutive_failures_reached"
    if int(state.get("consecutive_idle_cycles", 0)) >= max_idle_cycles:
        return True, "max_consecutive_idle_cycles_reached"
    return False, None


def run_factory_daemon(args):
    state_path = Path(args.state_output)
    journal_path = Path(args.journal_output)
    cycle_output = Path(args.cycle_output)

    state = _read_json(state_path, _initial_state())
    completed_cycles = 0

    while True:
        artifact = {}
        error = None

        try:
            artifact = run_autonomous_factory_cycle(
                portfolio_state=args.portfolio_state,
                ledger=args.ledger,
                policy=args.policy,
                top_k=args.top_k,
                output=str(cycle_output),
            )
        except SystemExit as exc:
            error = exc
            if cycle_output.exists():
                artifact = _read_json(cycle_output, {})
            else:
                artifact = {
                    "decision": {"action": "governed_run", "reason": "system_exit"},
                    "cycle_result": {"abort_reason": f"system_exit_{exc.code}"},
                    "status": "failed",
                }
        except Exception as exc:
            error = exc
            if cycle_output.exists():
                artifact = _read_json(cycle_output, {})
            else:
                artifact = {
                    "decision": {"action": "governed_run", "reason": "exception"},
                    "cycle_result": {"abort_reason": "exception"},
                    "status": "failed",
                }

        status = _extract_status(artifact, error=error)
        state = _update_state(state, artifact, status=status)
        _write_json(state_path, state)

        journal_entry = _build_journal_entry(artifact, status=status, error=error)
        _append_jsonl(journal_path, journal_entry)

        print(
            f"factory cycle {state['cycle_count']}: "
            f"decision={state['last_decision']} "
            f"risk={state['last_risk_level']} "
            f"status={state['last_cycle_status']}"
        )

        stop, reason = _should_stop(
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

    args = parser.parse_args(argv)
    raise SystemExit(run_factory_daemon(args))


if __name__ == "__main__":
    main()
