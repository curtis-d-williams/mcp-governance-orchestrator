# SPDX-License-Identifier: MIT
"""Phase L: governance enforcement policy evaluation.

Reads cycle_history.json (Phase I), cycle_history_summary.json (Phase J),
and a governance_policy.json.  Internally runs regression detection (Phase K),
evaluates the policy against the detected signals, and writes a governance
decision record.

Decision values
  continue — no regression, or regression fully suppressed by policy
  warn     — regression present but signals are in the allowed list
  abort    — a signal in abort_on_signals was detected

Policy schema
  {
    "on_regression":    "warn" | "abort" | "ignore",
    "abort_on_signals": ["status_regressed", ...],
    "allow_if_only":    ["action_set_changed", ...]
  }

Evaluation order (highest priority first)
  1. abort_on_signals — any matching signal forces abort
  2. allow_if_only    — if ALL signals are in this list, decision = warn
  3. on_regression    — applied to remaining regression cases
                        ("ignore" maps to "continue")

Usage:
    python3 scripts/enforce_governance_policy.py \\
        --history  artifacts/cycle_history.json \\
        --summary  artifacts/cycle_history_summary.json \\
        --policy   governance_policy.json \\
        --output   artifacts/governance_decision.json

Exit codes:
    0  — decision written (continue / warn / abort are all valid outcomes)
    1  — error (unreadable input, bad JSON, invalid schema)
"""

import argparse
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path


# ---------------------------------------------------------------------------
# JSON helper
# ---------------------------------------------------------------------------

def _write_json(path, data):
    """Write *data* as deterministic JSON (indent=2, sort_keys, trailing newline)."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Detector loader
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[1]

_VALID_ON_REGRESSION = frozenset({"warn", "abort", "ignore"})


def _load_detector():
    """Import detect_cycle_history_regression and return its entry-point function."""
    script = _REPO_ROOT / "scripts" / "detect_cycle_history_regression.py"
    spec = importlib.util.spec_from_file_location(
        "detect_cycle_history_regression", script
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.detect_cycle_history_regression


# ---------------------------------------------------------------------------
# Policy loading
# ---------------------------------------------------------------------------

def _load_policy(policy_path):
    """Read and validate the governance policy file.

    Returns:
        (policy_dict, None) on success.
        (None, error_string)  on failure.
    """
    try:
        raw = Path(policy_path).read_text(encoding="utf-8")
        policy = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"cannot read policy: {exc}"

    if not isinstance(policy, dict):
        return None, "policy must be a JSON object"

    on_regression = policy.get("on_regression")
    if on_regression not in _VALID_ON_REGRESSION:
        return None, (
            f"policy.on_regression must be one of "
            f"{sorted(_VALID_ON_REGRESSION)}, got {on_regression!r}"
        )

    if not isinstance(policy.get("abort_on_signals", []), list):
        return None, "policy.abort_on_signals must be a list"

    if not isinstance(policy.get("allow_if_only", []), list):
        return None, "policy.allow_if_only must be a list"

    if not isinstance(policy.get("capability_score_gate", {}), dict):
        return None, "policy.capability_score_gate must be a dict"

    return policy, None


# ---------------------------------------------------------------------------
# Capability score gate
# ---------------------------------------------------------------------------

def _load_capability_ledger(path):
    """Load a capability effectiveness ledger. Returns {} on None path or any error."""
    if path is None:
        return {}
    try:
        raw = Path(path).read_text(encoding="utf-8")
        ledger = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(ledger, dict):
        return {}
    return ledger


def _evaluate_capability_score_gate(capability_ledger, policy):
    """Return an abort decision dict when any gated capability falls below threshold.

    policy.capability_score_gate maps capability names to minimum smoothed
    success-rate thresholds (Laplace: (ok+1)/(total+2)).  Returns None when:
    - no capability_score_gate key in policy
    - capability_ledger is absent or has no 'capabilities' dict
    - all gated capabilities meet their thresholds
    - a gated capability has no history in the ledger (skipped, not failed)
    Returns an abort dict for the first failing capability (sorted deterministically).
    """
    gate = policy.get("capability_score_gate")
    if not gate or not isinstance(gate, dict):
        return None
    if not capability_ledger:
        return None
    caps = capability_ledger.get("capabilities")
    if not isinstance(caps, dict):
        return None

    failures = []
    for capability in sorted(gate.keys()):
        threshold = gate[capability]
        try:
            threshold = float(threshold)
        except (TypeError, ValueError):
            continue
        row = caps.get(capability)
        if not isinstance(row, dict):
            continue  # no history — gate does not fire on unknown capabilities
        total = row.get("total_syntheses", 0)
        success = row.get("successful_syntheses", 0)
        try:
            total = float(total)
            success = float(success)
        except (TypeError, ValueError):
            continue
        success_rate = (success + 1.0) / (total + 2.0)
        if success_rate < threshold:
            failures.append({
                "capability": capability,
                "success_rate": round(success_rate, 6),
                "threshold": threshold,
            })

    if not failures:
        return None
    return {
        "decision": "abort",
        "reason": f"capability_score_gate:{failures[0]['capability']}",
        "capability_score_gate_failures": failures,
    }


# ---------------------------------------------------------------------------
# Policy evaluation
# ---------------------------------------------------------------------------

def _map_on_regression(on_regression):
    """Map policy on_regression value to a governance decision string."""
    if on_regression == "ignore":
        return "continue"
    return on_regression  # "warn" or "abort"


def _evaluate_policy(regression_report, policy):
    """Return a governance decision dict.

    Args:
        regression_report: dict produced by detect_cycle_history_regression.
        policy:            validated policy dict.

    Returns:
        governance decision dict (always contains 'decision').
    """
    regression_detected = regression_report.get("regression_detected", False)
    signals = regression_report.get("signals", [])
    signal_types = [s["type"] for s in signals]

    base = {
        "policy_applied": policy,
        "regression_detected": regression_detected,
        "signals": signals,
    }

    if not regression_detected:
        return {**base, "decision": "continue"}

    abort_on = set(policy.get("abort_on_signals", []))
    allow_only = set(policy.get("allow_if_only", []))
    on_regression = policy.get("on_regression", "warn")

    # Priority 1: abort_on_signals — any match forces abort.
    # Iterate in sorted order for deterministic reason selection.
    for sig_type in sorted(signal_types):
        if sig_type in abort_on:
            return {**base, "decision": "abort", "reason": sig_type}

    # Priority 2: allow_if_only — if every signal is in the allowed set, warn.
    if allow_only and all(t in allow_only for t in signal_types):
        return {**base, "decision": "warn"}

    # Priority 3: on_regression policy fallback.
    return {**base, "decision": _map_on_regression(on_regression)}


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def enforce_governance_policy(history_path, summary_path, policy_path, output_path,
                               capability_ledger_path=None):
    """Evaluate governance policy and write a decision record.

    Args:
        history_path:           Path to cycle_history.json (Phase I output).
        summary_path:           Path to cycle_history_summary.json (Phase J output).
        policy_path:            Path to governance_policy.json.
        output_path:            Destination for the governance decision JSON.
        capability_ledger_path: Optional path to capability_effectiveness_ledger.json.
                                When provided and policy contains capability_score_gate,
                                gates are evaluated before regression detection.

    Returns:
        0 on success, 1 on error.
    """
    # --- Load and validate policy ---
    policy, err = _load_policy(policy_path)
    if err:
        sys.stderr.write(f"error: {err}\n")
        return 1

    # --- Evaluate capability score gate (pre-regression check) ---
    capability_ledger = _load_capability_ledger(capability_ledger_path)
    gate_result = _evaluate_capability_score_gate(capability_ledger, policy)
    if gate_result is not None:
        _write_json(output_path, {
            "policy_applied": policy,
            "regression_detected": False,
            "signals": [],
            **gate_result,
        })
        return 0

    # --- Run Phase K detector into a temporary file ---
    detect = _load_detector()
    fd, tmp_path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    try:
        rc = detect(history_path, summary_path, tmp_path)
        if rc != 0:
            return 1

        regression_report = json.loads(
            Path(tmp_path).read_text(encoding="utf-8")
        )
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    # --- Evaluate policy against regression report ---
    decision = _evaluate_policy(regression_report, policy)
    _write_json(output_path, decision)
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate governance policy against cycle history regression (Phase L)."
        ),
        add_help=True,
    )
    parser.add_argument("--history", required=True, metavar="FILE",
                        help="Path to cycle_history.json.")
    parser.add_argument("--summary", required=True, metavar="FILE",
                        help="Path to cycle_history_summary.json.")
    parser.add_argument("--policy", required=True, metavar="FILE",
                        help="Path to governance_policy.json.")
    parser.add_argument("--output", required=True, metavar="FILE",
                        help="Output path for the governance decision JSON.")
    parser.add_argument("--capability-ledger", default=None, metavar="FILE",
                        dest="capability_ledger",
                        help="Path to capability_effectiveness_ledger.json (optional).")

    args = parser.parse_args(argv)
    sys.exit(enforce_governance_policy(
        args.history, args.summary, args.policy, args.output,
        capability_ledger_path=args.capability_ledger,
    ))


if __name__ == "__main__":
    main()
