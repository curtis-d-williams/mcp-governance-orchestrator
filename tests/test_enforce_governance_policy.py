# SPDX-License-Identifier: MIT
"""Tests for scripts/enforce_governance_policy.py (Phase L).

Covers:
A. No regression — decision continue.
B. Allowed signals only — decision warn.
C. Abort signal present — decision abort.
D. Invalid policy file — rc=1.
E. Deterministic JSON output.
F. Policy combinations.
G. _evaluate_policy unit tests (pure function).
H. Error propagation from detector.
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Module loading
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from cycle_history_runtime import detect_cycle_history_regression

_SCRIPT = _REPO_ROOT / "scripts" / "enforce_governance_policy.py"
_spec = importlib.util.spec_from_file_location("enforce_governance_policy", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

enforce_governance_policy = _mod.enforce_governance_policy
_evaluate_policy = _mod._evaluate_policy
_load_policy = _mod._load_policy
_map_on_regression = _mod._map_on_regression

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_TS_EARLY = "2026-01-01T10:00:00.000000Z"
_TS_LATE  = "2026-03-10T20:43:46.008272Z"

# Two identical ok cycles — no regression
_CYCLE_OK_A = {
    "ledger_source": "work_dir",
    "selected_tasks": ["artifact_audit_example", "build_portfolio_dashboard"],
    "status": "ok",
    "timestamp": _TS_EARLY,
}
_CYCLE_OK_B = {
    "ledger_source": "work_dir",
    "selected_tasks": ["artifact_audit_example", "build_portfolio_dashboard"],
    "status": "ok",
    "timestamp": _TS_LATE,
}

# Different task set — triggers action_set_changed
_CYCLE_DIFFERENT_TASKS = {
    "ledger_source": "work_dir",
    "selected_tasks": ["artifact_audit_example"],
    "status": "ok",
    "timestamp": _TS_LATE,
}

# Aborted cycle — triggers status_regressed when previous was ok
_CYCLE_ABORTED = {
    "ledger_source": "none",
    "selected_tasks": None,
    "status": "aborted",
    "timestamp": _TS_LATE,
}

_SUMMARY_OK = {
    "average_tasks_selected_per_cycle": 2.0,
    "cycles_total": 2,
    "cycles_with_selected_tasks": 2,
    "ledger_source_counts": {"work_dir": 2},
    "most_recent_cycle_timestamp": _TS_LATE,
    "status_counts": {"ok": 2},
    "success_rate": 1.0,
    "task_selection_counts": {
        "artifact_audit_example": 2,
        "build_portfolio_dashboard": 2,
    },
    "unique_tasks_selected": 2,
}

# Standard policy: warn on regression; abort on status_regressed; allow action_set_changed
_POLICY_STANDARD = {
    "on_regression": "warn",
    "abort_on_signals": ["status_regressed"],
    "allow_if_only": ["action_set_changed"],
}


# ---------------------------------------------------------------------------
# Write helpers
# ---------------------------------------------------------------------------

def _write_history(tmp_path, cycles, name="cycle_history.json"):
    p = tmp_path / name
    p.write_text(
        json.dumps({"cycles": cycles}, indent=2) + "\n",
        encoding="utf-8",
    )
    return p


def _write_summary(tmp_path, data=None, name="cycle_history_summary.json"):
    p = tmp_path / name
    p.write_text(
        json.dumps(data if data is not None else _SUMMARY_OK, indent=2) + "\n",
        encoding="utf-8",
    )
    return p


def _write_policy(tmp_path, policy, name="governance_policy.json"):
    p = tmp_path / name
    p.write_text(
        json.dumps(policy, indent=2) + "\n",
        encoding="utf-8",
    )
    return p


def _run(tmp_path, cycles, policy=None, summary=None):
    """Write fixture files, run enforcer, return (rc, parsed_output_or_None)."""
    h = _write_history(tmp_path, cycles)
    s = _write_summary(tmp_path, summary)
    pol = _write_policy(tmp_path, policy if policy is not None else _POLICY_STANDARD)
    out = tmp_path / "governance_decision.json"
    rc = enforce_governance_policy(str(h), str(s), str(pol), str(out))
    data = json.loads(out.read_text(encoding="utf-8")) if out.exists() else None
    return rc, data


# ---------------------------------------------------------------------------
# A. No regression — decision continue
# ---------------------------------------------------------------------------

class TestNoRegression:
    def test_no_regression_returns_zero(self, tmp_path):
        rc, _ = _run(tmp_path, [_CYCLE_OK_A, _CYCLE_OK_B])
        assert rc == 0

    def test_no_regression_decision_continue(self, tmp_path):
        _, data = _run(tmp_path, [_CYCLE_OK_A, _CYCLE_OK_B])
        assert data["decision"] == "continue"

    def test_no_regression_regression_detected_false(self, tmp_path):
        _, data = _run(tmp_path, [_CYCLE_OK_A, _CYCLE_OK_B])
        assert data["regression_detected"] is False

    def test_no_regression_signals_empty(self, tmp_path):
        _, data = _run(tmp_path, [_CYCLE_OK_A, _CYCLE_OK_B])
        assert data["signals"] == []

    def test_no_regression_output_file_created(self, tmp_path):
        h = _write_history(tmp_path, [_CYCLE_OK_A, _CYCLE_OK_B])
        s = _write_summary(tmp_path)
        pol = _write_policy(tmp_path, _POLICY_STANDARD)
        out = tmp_path / "governance_decision.json"
        enforce_governance_policy(str(h), str(s), str(pol), str(out))
        assert out.exists()

    def test_insufficient_history_decision_continue(self, tmp_path):
        # Single cycle → insufficient history → no regression → continue
        _, data = _run(tmp_path, [_CYCLE_OK_A])
        assert data["decision"] == "continue"

    def test_zero_cycles_decision_continue(self, tmp_path):
        _, data = _run(tmp_path, [])
        assert data["decision"] == "continue"


# ---------------------------------------------------------------------------
# B. Allowed signals only — decision warn
# ---------------------------------------------------------------------------

class TestAllowedSignals:
    def test_allowed_signal_decision_warn(self, tmp_path):
        # action_set_changed only, which is in allow_if_only → warn
        _, data = _run(tmp_path, [_CYCLE_OK_A, _CYCLE_DIFFERENT_TASKS])
        assert data["decision"] == "warn"

    def test_allowed_signal_returns_zero(self, tmp_path):
        rc, _ = _run(tmp_path, [_CYCLE_OK_A, _CYCLE_DIFFERENT_TASKS])
        assert rc == 0

    def test_allowed_signal_regression_detected_true(self, tmp_path):
        _, data = _run(tmp_path, [_CYCLE_OK_A, _CYCLE_DIFFERENT_TASKS])
        assert data["regression_detected"] is True

    def test_allowed_signal_signals_present(self, tmp_path):
        _, data = _run(tmp_path, [_CYCLE_OK_A, _CYCLE_DIFFERENT_TASKS])
        assert len(data["signals"]) > 0

    def test_allowed_signal_signal_type_action_set_changed(self, tmp_path):
        _, data = _run(tmp_path, [_CYCLE_OK_A, _CYCLE_DIFFERENT_TASKS])
        types = [s["type"] for s in data["signals"]]
        assert "action_set_changed" in types

    def test_allowed_signal_policy_applied_present(self, tmp_path):
        _, data = _run(tmp_path, [_CYCLE_OK_A, _CYCLE_DIFFERENT_TASKS])
        assert "policy_applied" in data


# ---------------------------------------------------------------------------
# C. Abort signal present — decision abort
# ---------------------------------------------------------------------------

class TestAbortSignal:
    def test_abort_signal_decision_abort(self, tmp_path):
        # ok → aborted triggers status_regressed which is in abort_on_signals
        _, data = _run(tmp_path, [_CYCLE_OK_A, _CYCLE_ABORTED])
        assert data["decision"] == "abort"

    def test_abort_signal_returns_zero(self, tmp_path):
        # rc=0 even for abort: abort is a valid governance outcome, not an error
        rc, _ = _run(tmp_path, [_CYCLE_OK_A, _CYCLE_ABORTED])
        assert rc == 0

    def test_abort_signal_reason_present(self, tmp_path):
        _, data = _run(tmp_path, [_CYCLE_OK_A, _CYCLE_ABORTED])
        assert "reason" in data

    def test_abort_signal_reason_is_status_regressed(self, tmp_path):
        _, data = _run(tmp_path, [_CYCLE_OK_A, _CYCLE_ABORTED])
        assert data["reason"] == "status_regressed"

    def test_abort_signal_regression_detected_true(self, tmp_path):
        _, data = _run(tmp_path, [_CYCLE_OK_A, _CYCLE_ABORTED])
        assert data["regression_detected"] is True

    def test_abort_signal_signals_non_empty(self, tmp_path):
        _, data = _run(tmp_path, [_CYCLE_OK_A, _CYCLE_ABORTED])
        assert len(data["signals"]) > 0

    def test_abort_takes_priority_over_allow_if_only(self, tmp_path):
        # Policy: allow_if_only includes status_regressed AND abort_on_signals also has it
        # abort_on_signals must take priority
        policy = {
            "on_regression": "warn",
            "abort_on_signals": ["status_regressed"],
            "allow_if_only": ["status_regressed"],
        }
        _, data = _run(tmp_path, [_CYCLE_OK_A, _CYCLE_ABORTED], policy=policy)
        assert data["decision"] == "abort"


# ---------------------------------------------------------------------------
# D. Invalid policy file — rc=1
# ---------------------------------------------------------------------------

class TestInvalidPolicy:
    def test_missing_policy_returns_one(self, tmp_path):
        h = _write_history(tmp_path, [_CYCLE_OK_A, _CYCLE_OK_B])
        s = _write_summary(tmp_path)
        out = tmp_path / "out.json"
        rc = enforce_governance_policy(
            str(h), str(s), str(tmp_path / "nonexistent.json"), str(out)
        )
        assert rc == 1

    def test_missing_policy_no_output_created(self, tmp_path):
        h = _write_history(tmp_path, [_CYCLE_OK_A, _CYCLE_OK_B])
        s = _write_summary(tmp_path)
        out = tmp_path / "out.json"
        enforce_governance_policy(
            str(h), str(s), str(tmp_path / "nonexistent.json"), str(out)
        )
        assert not out.exists()

    def test_bad_json_policy_returns_one(self, tmp_path):
        h = _write_history(tmp_path, [_CYCLE_OK_A, _CYCLE_OK_B])
        s = _write_summary(tmp_path)
        bad = tmp_path / "bad_policy.json"
        bad.write_text("not json{{", encoding="utf-8")
        out = tmp_path / "out.json"
        rc = enforce_governance_policy(str(h), str(s), str(bad), str(out))
        assert rc == 1

    def test_policy_root_is_list_returns_one(self, tmp_path):
        h = _write_history(tmp_path, [_CYCLE_OK_A, _CYCLE_OK_B])
        s = _write_summary(tmp_path)
        bad = tmp_path / "bad_policy.json"
        bad.write_text(json.dumps([]) + "\n", encoding="utf-8")
        out = tmp_path / "out.json"
        rc = enforce_governance_policy(str(h), str(s), str(bad), str(out))
        assert rc == 1

    def test_invalid_on_regression_returns_one(self, tmp_path):
        h = _write_history(tmp_path, [_CYCLE_OK_A, _CYCLE_OK_B])
        s = _write_summary(tmp_path)
        bad_policy = {
            "on_regression": "explode",
            "abort_on_signals": [],
            "allow_if_only": [],
        }
        pol = _write_policy(tmp_path, bad_policy)
        out = tmp_path / "out.json"
        rc = enforce_governance_policy(str(h), str(s), str(pol), str(out))
        assert rc == 1

    def test_missing_on_regression_returns_one(self, tmp_path):
        h = _write_history(tmp_path, [_CYCLE_OK_A, _CYCLE_OK_B])
        s = _write_summary(tmp_path)
        bad_policy = {
            "abort_on_signals": [],
            "allow_if_only": [],
        }
        pol = _write_policy(tmp_path, bad_policy)
        out = tmp_path / "out.json"
        rc = enforce_governance_policy(str(h), str(s), str(pol), str(out))
        assert rc == 1

    def test_abort_on_signals_not_list_returns_one(self, tmp_path):
        h = _write_history(tmp_path, [_CYCLE_OK_A, _CYCLE_OK_B])
        s = _write_summary(tmp_path)
        bad_policy = {
            "on_regression": "warn",
            "abort_on_signals": "status_regressed",
            "allow_if_only": [],
        }
        pol = _write_policy(tmp_path, bad_policy)
        out = tmp_path / "out.json"
        rc = enforce_governance_policy(str(h), str(s), str(pol), str(out))
        assert rc == 1

    def test_allow_if_only_not_list_returns_one(self, tmp_path):
        h = _write_history(tmp_path, [_CYCLE_OK_A, _CYCLE_OK_B])
        s = _write_summary(tmp_path)
        bad_policy = {
            "on_regression": "warn",
            "abort_on_signals": [],
            "allow_if_only": "action_set_changed",
        }
        pol = _write_policy(tmp_path, bad_policy)
        out = tmp_path / "out.json"
        rc = enforce_governance_policy(str(h), str(s), str(pol), str(out))
        assert rc == 1

    def test_invalid_history_returns_one(self, tmp_path):
        s = _write_summary(tmp_path)
        pol = _write_policy(tmp_path, _POLICY_STANDARD)
        out = tmp_path / "out.json"
        rc = enforce_governance_policy(
            str(tmp_path / "nonexistent.json"), str(s), str(pol), str(out)
        )
        assert rc == 1

    def test_invalid_summary_returns_one(self, tmp_path):
        h = _write_history(tmp_path, [_CYCLE_OK_A, _CYCLE_OK_B])
        pol = _write_policy(tmp_path, _POLICY_STANDARD)
        out = tmp_path / "out.json"
        rc = enforce_governance_policy(
            str(h), str(tmp_path / "nonexistent.json"), str(pol), str(out)
        )
        assert rc == 1


# ---------------------------------------------------------------------------
# E. Deterministic JSON output
# ---------------------------------------------------------------------------

class TestDeterministicOutput:
    def test_trailing_newline(self, tmp_path):
        h = _write_history(tmp_path, [_CYCLE_OK_A, _CYCLE_OK_B])
        s = _write_summary(tmp_path)
        pol = _write_policy(tmp_path, _POLICY_STANDARD)
        out = tmp_path / "out.json"
        enforce_governance_policy(str(h), str(s), str(pol), str(out))
        assert out.read_text(encoding="utf-8").endswith("\n")

    def test_sort_keys_alphabetical(self, tmp_path):
        h = _write_history(tmp_path, [_CYCLE_OK_A, _CYCLE_OK_B])
        s = _write_summary(tmp_path)
        pol = _write_policy(tmp_path, _POLICY_STANDARD)
        out = tmp_path / "out.json"
        enforce_governance_policy(str(h), str(s), str(pol), str(out))
        raw = out.read_text(encoding="utf-8")
        data = json.loads(raw)
        assert raw == json.dumps(data, indent=2, sort_keys=True) + "\n"

    def test_same_input_same_output(self, tmp_path):
        h = _write_history(tmp_path, [_CYCLE_OK_A, _CYCLE_OK_B])
        s = _write_summary(tmp_path)
        pol = _write_policy(tmp_path, _POLICY_STANDARD)
        out1 = tmp_path / "r1.json"
        out2 = tmp_path / "r2.json"
        enforce_governance_policy(str(h), str(s), str(pol), str(out1))
        enforce_governance_policy(str(h), str(s), str(pol), str(out2))
        assert out1.read_text(encoding="utf-8") == out2.read_text(encoding="utf-8")

    def test_required_top_level_fields_continue(self, tmp_path):
        _, data = _run(tmp_path, [_CYCLE_OK_A, _CYCLE_OK_B])
        required = {"decision", "policy_applied", "regression_detected", "signals"}
        assert required <= set(data.keys())

    def test_required_top_level_fields_abort(self, tmp_path):
        _, data = _run(tmp_path, [_CYCLE_OK_A, _CYCLE_ABORTED])
        assert "reason" in data
        required = {"decision", "policy_applied", "reason", "regression_detected", "signals"}
        assert required <= set(data.keys())

    def test_creates_parent_dirs(self, tmp_path):
        h = _write_history(tmp_path, [_CYCLE_OK_A, _CYCLE_OK_B])
        s = _write_summary(tmp_path)
        pol = _write_policy(tmp_path, _POLICY_STANDARD)
        out = tmp_path / "sub" / "nested" / "decision.json"
        rc = enforce_governance_policy(str(h), str(s), str(pol), str(out))
        assert rc == 0
        assert out.exists()

    def test_policy_applied_matches_input_policy(self, tmp_path):
        _, data = _run(tmp_path, [_CYCLE_OK_A, _CYCLE_OK_B])
        assert data["policy_applied"] == _POLICY_STANDARD


# ---------------------------------------------------------------------------
# F. Policy combinations
# ---------------------------------------------------------------------------

class TestPolicyCombinations:
    def test_on_regression_abort_no_allow_aborts(self, tmp_path):
        # on_regression=abort, no allow_if_only, action_set_changed not in abort_on_signals
        # → falls to on_regression=abort → decision abort
        policy = {
            "on_regression": "abort",
            "abort_on_signals": [],
            "allow_if_only": [],
        }
        _, data = _run(tmp_path, [_CYCLE_OK_A, _CYCLE_DIFFERENT_TASKS], policy=policy)
        assert data["decision"] == "abort"

    def test_on_regression_abort_with_allow_warns(self, tmp_path):
        # on_regression=abort but action_set_changed is in allow_if_only
        # → allow_if_only takes priority → decision warn (not abort)
        policy = {
            "on_regression": "abort",
            "abort_on_signals": ["status_regressed"],
            "allow_if_only": ["action_set_changed"],
        }
        _, data = _run(tmp_path, [_CYCLE_OK_A, _CYCLE_DIFFERENT_TASKS], policy=policy)
        assert data["decision"] == "warn"

    def test_on_regression_ignore_maps_to_continue(self, tmp_path):
        # on_regression=ignore, signal not in abort_on_signals, not all in allow_if_only
        policy = {
            "on_regression": "ignore",
            "abort_on_signals": [],
            "allow_if_only": [],
        }
        _, data = _run(tmp_path, [_CYCLE_OK_A, _CYCLE_DIFFERENT_TASKS], policy=policy)
        assert data["decision"] == "continue"

    def test_on_regression_warn_without_allow_warns(self, tmp_path):
        # on_regression=warn, no allow_if_only, signal not in abort_on_signals
        policy = {
            "on_regression": "warn",
            "abort_on_signals": [],
            "allow_if_only": [],
        }
        _, data = _run(tmp_path, [_CYCLE_OK_A, _CYCLE_DIFFERENT_TASKS], policy=policy)
        assert data["decision"] == "warn"

    def test_empty_abort_and_allow_uses_on_regression(self, tmp_path):
        # Both lists empty; on_regression=warn → warn
        policy = {
            "on_regression": "warn",
            "abort_on_signals": [],
            "allow_if_only": [],
        }
        _, data = _run(tmp_path, [_CYCLE_OK_A, _CYCLE_ABORTED], policy=policy)
        assert data["decision"] == "warn"

    def test_abort_on_signals_beats_on_regression_ignore(self, tmp_path):
        # Even if on_regression=ignore, abort_on_signals forces abort
        policy = {
            "on_regression": "ignore",
            "abort_on_signals": ["status_regressed"],
            "allow_if_only": [],
        }
        _, data = _run(tmp_path, [_CYCLE_OK_A, _CYCLE_ABORTED], policy=policy)
        assert data["decision"] == "abort"

    def test_allow_if_only_partial_match_falls_to_on_regression(self, tmp_path):
        # Signals: action_set_changed + status_regressed
        # abort_on_signals: []  allow_if_only: [action_set_changed]
        # NOT all signals in allow_only → falls to on_regression=warn
        policy = {
            "on_regression": "warn",
            "abort_on_signals": [],
            "allow_if_only": ["action_set_changed"],
        }
        _, data = _run(tmp_path, [_CYCLE_OK_A, _CYCLE_ABORTED], policy=policy)
        # action_set_changed is allowed but status_regressed is not
        # → partial match, not all in allow_if_only → on_regression=warn
        assert data["decision"] == "warn"

    def test_no_regression_ignores_abort_on_signals(self, tmp_path):
        # Even with abort_on_signals populated, no regression means continue
        policy = {
            "on_regression": "abort",
            "abort_on_signals": ["action_set_changed", "status_regressed"],
            "allow_if_only": [],
        }
        _, data = _run(tmp_path, [_CYCLE_OK_A, _CYCLE_OK_B], policy=policy)
        assert data["decision"] == "continue"

    def test_policy_applied_in_abort_output(self, tmp_path):
        _, data = _run(tmp_path, [_CYCLE_OK_A, _CYCLE_ABORTED])
        assert data["policy_applied"] == _POLICY_STANDARD

    def test_reason_uses_first_alphabetical_abort_signal(self, tmp_path):
        # Both action_set_changed and status_regressed in abort_on_signals.
        # ok→aborted triggers both signals; alphabetically action_set_changed < status_regressed.
        policy = {
            "on_regression": "warn",
            "abort_on_signals": ["action_set_changed", "status_regressed"],
            "allow_if_only": [],
        }
        _, data = _run(tmp_path, [_CYCLE_OK_A, _CYCLE_ABORTED], policy=policy)
        assert data["decision"] == "abort"
        assert data["reason"] == "action_set_changed"


# ---------------------------------------------------------------------------
# G. _evaluate_policy unit tests (pure function)
# ---------------------------------------------------------------------------

class TestEvaluatePolicyUnit:
    """Test _evaluate_policy directly with synthetic regression reports."""

    def _report(self, regression_detected, signal_types):
        """Build a minimal regression report dict."""
        signals = [{"type": t} for t in signal_types]
        return {
            "regression_detected": regression_detected,
            "signals": signals,
        }

    def test_no_regression_continue(self):
        report = self._report(False, [])
        result = _evaluate_policy(report, _POLICY_STANDARD)
        assert result["decision"] == "continue"

    def test_allowed_signal_warn(self):
        report = self._report(True, ["action_set_changed"])
        result = _evaluate_policy(report, _POLICY_STANDARD)
        assert result["decision"] == "warn"

    def test_abort_signal_abort(self):
        report = self._report(True, ["status_regressed"])
        result = _evaluate_policy(report, _POLICY_STANDARD)
        assert result["decision"] == "abort"

    def test_abort_signal_reason(self):
        report = self._report(True, ["status_regressed"])
        result = _evaluate_policy(report, _POLICY_STANDARD)
        assert result["reason"] == "status_regressed"

    def test_abort_takes_priority_over_allow(self):
        report = self._report(True, ["action_set_changed"])
        policy = {
            "on_regression": "warn",
            "abort_on_signals": ["action_set_changed"],
            "allow_if_only": ["action_set_changed"],
        }
        result = _evaluate_policy(report, policy)
        assert result["decision"] == "abort"

    def test_on_regression_ignore_returns_continue(self):
        report = self._report(True, ["action_set_changed"])
        policy = {
            "on_regression": "ignore",
            "abort_on_signals": [],
            "allow_if_only": [],
        }
        result = _evaluate_policy(report, policy)
        assert result["decision"] == "continue"

    def test_signals_passed_through_in_result(self):
        report = self._report(True, ["action_set_changed"])
        result = _evaluate_policy(report, _POLICY_STANDARD)
        assert result["signals"] == report["signals"]

    def test_policy_applied_passed_through(self):
        report = self._report(False, [])
        result = _evaluate_policy(report, _POLICY_STANDARD)
        assert result["policy_applied"] is _POLICY_STANDARD

    def test_partial_allow_if_only_falls_to_on_regression(self):
        # Signals: ["action_set_changed", "status_regressed"]
        # allow_if_only: ["action_set_changed"] — not all signals allowed
        report = self._report(True, ["action_set_changed", "status_regressed"])
        policy = {
            "on_regression": "warn",
            "abort_on_signals": [],
            "allow_if_only": ["action_set_changed"],
        }
        result = _evaluate_policy(report, policy)
        assert result["decision"] == "warn"  # on_regression=warn

    def test_all_signals_in_allow_if_only_warns(self):
        report = self._report(True, ["action_set_changed"])
        policy = {
            "on_regression": "abort",   # would abort if not for allow_if_only
            "abort_on_signals": [],
            "allow_if_only": ["action_set_changed"],
        }
        result = _evaluate_policy(report, policy)
        assert result["decision"] == "warn"

    def test_empty_allow_if_only_with_regression_applies_on_regression(self):
        report = self._report(True, ["action_set_changed"])
        policy = {
            "on_regression": "warn",
            "abort_on_signals": [],
            "allow_if_only": [],
        }
        result = _evaluate_policy(report, policy)
        assert result["decision"] == "warn"


# ---------------------------------------------------------------------------
# H. Error propagation from detector
# ---------------------------------------------------------------------------

class TestDetectorErrorPropagation:
    def test_bad_history_rc_one(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("not json{{", encoding="utf-8")
        s = _write_summary(tmp_path)
        pol = _write_policy(tmp_path, _POLICY_STANDARD)
        out = tmp_path / "out.json"
        rc = enforce_governance_policy(str(bad), str(s), str(pol), str(out))
        assert rc == 1

    def test_bad_history_no_output_created(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("not json{{", encoding="utf-8")
        s = _write_summary(tmp_path)
        pol = _write_policy(tmp_path, _POLICY_STANDARD)
        out = tmp_path / "out.json"
        enforce_governance_policy(str(bad), str(s), str(pol), str(out))
        assert not out.exists()


# ---------------------------------------------------------------------------
# I. _load_policy unit tests
# ---------------------------------------------------------------------------

class TestLoadPolicyUnit:
    def _write(self, tmp_path, data):
        p = tmp_path / "policy.json"
        p.write_text(json.dumps(data) + "\n", encoding="utf-8")
        return str(p)

    def test_valid_policy_returns_dict(self, tmp_path):
        path = self._write(tmp_path, _POLICY_STANDARD)
        policy, err = _load_policy(path)
        assert policy is not None
        assert err is None

    def test_missing_file_returns_error(self, tmp_path):
        policy, err = _load_policy(str(tmp_path / "nope.json"))
        assert policy is None
        assert err is not None

    def test_invalid_on_regression_returns_error(self, tmp_path):
        bad = {**_POLICY_STANDARD, "on_regression": "crash"}
        path = self._write(tmp_path, bad)
        policy, err = _load_policy(path)
        assert policy is None
        assert err is not None

    def test_warn_on_regression_valid(self, tmp_path):
        p = {**_POLICY_STANDARD, "on_regression": "warn"}
        path = self._write(tmp_path, p)
        policy, err = _load_policy(path)
        assert err is None

    def test_abort_on_regression_valid(self, tmp_path):
        p = {**_POLICY_STANDARD, "on_regression": "abort"}
        path = self._write(tmp_path, p)
        policy, err = _load_policy(path)
        assert err is None

    def test_ignore_on_regression_valid(self, tmp_path):
        p = {**_POLICY_STANDARD, "on_regression": "ignore"}
        path = self._write(tmp_path, p)
        policy, err = _load_policy(path)
        assert err is None


# ---------------------------------------------------------------------------
# J. _map_on_regression unit tests
# ---------------------------------------------------------------------------

class TestMapOnRegression:
    def test_warn_maps_to_warn(self):
        assert _map_on_regression("warn") == "warn"

    def test_abort_maps_to_abort(self):
        assert _map_on_regression("abort") == "abort"

    def test_ignore_maps_to_continue(self):
        assert _map_on_regression("ignore") == "continue"


# ---------------------------------------------------------------------------
# K. Phase K / Phase L signal consistency
# ---------------------------------------------------------------------------

class TestKLSignalConsistency:
    """Phase L must surface the same regression_detected and signals as Phase K."""

    def _setup(self, tmp_path):
        h = _write_history(tmp_path, [_CYCLE_OK_A, _CYCLE_ABORTED])
        s = _write_summary(tmp_path)
        pol = _write_policy(tmp_path, _POLICY_STANDARD)

        k_out = tmp_path / "k_regression.json"
        k_rc = detect_cycle_history_regression(str(h), str(s), str(k_out))
        assert k_rc == 0, f"Phase K failed with rc={k_rc}"
        k_data = json.loads(k_out.read_text(encoding="utf-8"))

        l_out = tmp_path / "l_decision.json"
        enforce_governance_policy(str(h), str(s), str(pol), str(l_out))
        l_data = json.loads(l_out.read_text(encoding="utf-8"))

        return k_data, l_data

    def test_phase_l_regression_detected_matches_phase_k(self, tmp_path):
        k_data, l_data = self._setup(tmp_path)
        assert l_data["regression_detected"] == k_data["regression_detected"]

    def test_phase_l_signals_match_phase_k(self, tmp_path):
        k_data, l_data = self._setup(tmp_path)
        assert l_data["signals"] == k_data["signals"]
