# SPDX-License-Identifier: MIT
"""Tests for scripts/detect_cycle_history_regression.py (Phase K).

Covers:
A. Insufficient history — 0 and 1 cycles.
B. No regression — identical consecutive cycles.
C. action_set_changed — task set differs between current and previous.
D. status_regressed — ok → aborted.
E. Status improved — aborted → ok (no regression).
F. Both signals present simultaneously.
G. Deterministic output formatting.
H. Invalid history file handling.
I. Invalid summary file handling.
J. Invalid schema handling.
K. Summary context pass-through.
L. _detect_signals unit tests (pure function).
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

_SCRIPT = _REPO_ROOT / "scripts" / "detect_cycle_history_regression.py"
_spec = importlib.util.spec_from_file_location(
    "detect_cycle_history_regression", _SCRIPT
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

detect_cycle_history_regression = _mod.detect_cycle_history_regression
_detect_signals = _mod._detect_signals
_status_rank = _mod._status_rank
_sorted_tasks = _mod._sorted_tasks

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_TS_EARLY = "2026-01-01T10:00:00.000000Z"
_TS_MID   = "2026-03-10T20:42:52.576291Z"
_TS_LATE  = "2026-03-10T20:43:46.008272Z"

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

_CYCLE_OK_A = {
    "ledger_source": "work_dir",
    "selected_tasks": ["artifact_audit_example", "build_portfolio_dashboard"],
    "status": "ok",
    "timestamp": _TS_MID,
}

_CYCLE_OK_B = {
    "ledger_source": "work_dir",
    "selected_tasks": ["artifact_audit_example", "build_portfolio_dashboard"],
    "status": "ok",
    "timestamp": _TS_LATE,
}

_CYCLE_OK_DIFFERENT_TASKS = {
    "ledger_source": "work_dir",
    "selected_tasks": ["artifact_audit_example"],
    "status": "ok",
    "timestamp": _TS_LATE,
}

_CYCLE_ABORTED = {
    "ledger_source": "none",
    "selected_tasks": None,
    "status": "aborted",
    "timestamp": _TS_LATE,
}

_CYCLE_ABORTED_EARLY = {
    "ledger_source": "none",
    "selected_tasks": None,
    "status": "aborted",
    "timestamp": _TS_MID,
}


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


def _run(tmp_path, cycles, summary=None):
    """Write fixtures, run detector, return parsed report."""
    h = _write_history(tmp_path, cycles)
    s = _write_summary(tmp_path, summary)
    out = tmp_path / "regression.json"
    rc = detect_cycle_history_regression(str(h), str(s), str(out))
    data = json.loads(out.read_text()) if out.exists() else None
    return rc, data


# ---------------------------------------------------------------------------
# A. Insufficient history
# ---------------------------------------------------------------------------

class TestInsufficientHistory:
    def test_zero_cycles_returns_zero(self, tmp_path):
        rc, _ = _run(tmp_path, [])
        assert rc == 0

    def test_zero_cycles_insufficient_history_true(self, tmp_path):
        _, data = _run(tmp_path, [])
        assert data["insufficient_history"] is True

    def test_zero_cycles_regression_detected_false(self, tmp_path):
        _, data = _run(tmp_path, [])
        assert data["regression_detected"] is False

    def test_zero_cycles_signals_empty(self, tmp_path):
        _, data = _run(tmp_path, [])
        assert data["signals"] == []

    def test_zero_cycles_current_timestamp_none(self, tmp_path):
        _, data = _run(tmp_path, [])
        assert data["current_cycle_timestamp"] is None

    def test_one_cycle_returns_zero(self, tmp_path):
        rc, _ = _run(tmp_path, [_CYCLE_OK_A])
        assert rc == 0

    def test_one_cycle_insufficient_history_true(self, tmp_path):
        _, data = _run(tmp_path, [_CYCLE_OK_A])
        assert data["insufficient_history"] is True

    def test_one_cycle_regression_detected_false(self, tmp_path):
        _, data = _run(tmp_path, [_CYCLE_OK_A])
        assert data["regression_detected"] is False

    def test_one_cycle_current_timestamp_set(self, tmp_path):
        _, data = _run(tmp_path, [_CYCLE_OK_A])
        assert data["current_cycle_timestamp"] == _TS_MID

    def test_one_cycle_output_file_created(self, tmp_path):
        h = _write_history(tmp_path, [_CYCLE_OK_A])
        s = _write_summary(tmp_path)
        out = tmp_path / "regression.json"
        detect_cycle_history_regression(str(h), str(s), str(out))
        assert out.exists()


# ---------------------------------------------------------------------------
# B. No regression — identical consecutive cycles
# ---------------------------------------------------------------------------

class TestNoRegression:
    def test_identical_cycles_returns_zero(self, tmp_path):
        rc, _ = _run(tmp_path, [_CYCLE_OK_A, _CYCLE_OK_B])
        assert rc == 0

    def test_identical_cycles_regression_detected_false(self, tmp_path):
        _, data = _run(tmp_path, [_CYCLE_OK_A, _CYCLE_OK_B])
        assert data["regression_detected"] is False

    def test_identical_cycles_signals_empty(self, tmp_path):
        _, data = _run(tmp_path, [_CYCLE_OK_A, _CYCLE_OK_B])
        assert data["signals"] == []

    def test_identical_cycles_insufficient_history_false(self, tmp_path):
        _, data = _run(tmp_path, [_CYCLE_OK_A, _CYCLE_OK_B])
        assert data["insufficient_history"] is False

    def test_identical_cycles_current_timestamp(self, tmp_path):
        _, data = _run(tmp_path, [_CYCLE_OK_A, _CYCLE_OK_B])
        assert data["current_cycle_timestamp"] == _TS_LATE

    def test_aborted_then_aborted_no_regression(self, tmp_path):
        cycle_aborted_late = {**_CYCLE_ABORTED_EARLY, "timestamp": _TS_LATE}
        _, data = _run(tmp_path, [_CYCLE_ABORTED_EARLY, cycle_aborted_late])
        # same status, same tasks (both None→[]) → no regression
        assert data["regression_detected"] is False


# ---------------------------------------------------------------------------
# C. action_set_changed
# ---------------------------------------------------------------------------

class TestActionSetChanged:
    def test_different_tasks_regression_detected_true(self, tmp_path):
        _, data = _run(tmp_path, [_CYCLE_OK_A, _CYCLE_OK_DIFFERENT_TASKS])
        assert data["regression_detected"] is True

    def test_action_set_changed_signal_present(self, tmp_path):
        _, data = _run(tmp_path, [_CYCLE_OK_A, _CYCLE_OK_DIFFERENT_TASKS])
        types = [s["type"] for s in data["signals"]]
        assert "action_set_changed" in types

    def test_action_set_signal_previous_tasks_sorted(self, tmp_path):
        _, data = _run(tmp_path, [_CYCLE_OK_A, _CYCLE_OK_DIFFERENT_TASKS])
        sig = next(s for s in data["signals"] if s["type"] == "action_set_changed")
        assert sig["previous_selected_tasks"] == sorted(
            _CYCLE_OK_A["selected_tasks"]
        )

    def test_action_set_signal_current_tasks_sorted(self, tmp_path):
        _, data = _run(tmp_path, [_CYCLE_OK_A, _CYCLE_OK_DIFFERENT_TASKS])
        sig = next(s for s in data["signals"] if s["type"] == "action_set_changed")
        assert sig["current_selected_tasks"] == sorted(
            _CYCLE_OK_DIFFERENT_TASKS["selected_tasks"]
        )

    def test_task_order_does_not_affect_detection(self, tmp_path):
        """Task set comparison must be order-independent."""
        cycle_reversed = {
            **_CYCLE_OK_A,
            "selected_tasks": list(reversed(_CYCLE_OK_A["selected_tasks"])),
            "timestamp": _TS_LATE,
        }
        _, data = _run(tmp_path, [_CYCLE_OK_A, cycle_reversed])
        # same set, different order → no action_set_changed
        assert data["regression_detected"] is False

    def test_none_vs_empty_tasks_no_signal(self, tmp_path):
        """None and [] are both treated as empty task set — no change signal."""
        cycle_none = {**_CYCLE_ABORTED_EARLY}   # selected_tasks: None
        cycle_empty = {**_CYCLE_ABORTED_EARLY, "selected_tasks": [], "timestamp": _TS_LATE}
        _, data = _run(tmp_path, [cycle_none, cycle_empty])
        types = [s["type"] for s in data["signals"]]
        assert "action_set_changed" not in types

    def test_added_task_triggers_signal(self, tmp_path):
        cycle_more = {
            **_CYCLE_OK_A,
            "selected_tasks": [
                "artifact_audit_example",
                "build_portfolio_dashboard",
                "failure_recovery_example",
            ],
            "timestamp": _TS_LATE,
        }
        _, data = _run(tmp_path, [_CYCLE_OK_A, cycle_more])
        assert data["regression_detected"] is True
        types = [s["type"] for s in data["signals"]]
        assert "action_set_changed" in types


# ---------------------------------------------------------------------------
# D. status_regressed — ok → aborted
# ---------------------------------------------------------------------------

class TestStatusRegressed:
    def test_ok_to_aborted_regression_detected(self, tmp_path):
        _, data = _run(tmp_path, [_CYCLE_OK_A, _CYCLE_ABORTED])
        assert data["regression_detected"] is True

    def test_ok_to_aborted_signal_present(self, tmp_path):
        _, data = _run(tmp_path, [_CYCLE_OK_A, _CYCLE_ABORTED])
        types = [s["type"] for s in data["signals"]]
        assert "status_regressed" in types

    def test_status_signal_previous_ok(self, tmp_path):
        _, data = _run(tmp_path, [_CYCLE_OK_A, _CYCLE_ABORTED])
        sig = next(s for s in data["signals"] if s["type"] == "status_regressed")
        assert sig["previous_status"] == "ok"

    def test_status_signal_current_aborted(self, tmp_path):
        _, data = _run(tmp_path, [_CYCLE_OK_A, _CYCLE_ABORTED])
        sig = next(s for s in data["signals"] if s["type"] == "status_regressed")
        assert sig["current_status"] == "aborted"

    def test_ok_to_ok_no_status_regression(self, tmp_path):
        _, data = _run(tmp_path, [_CYCLE_OK_A, _CYCLE_OK_B])
        types = [s["type"] for s in data["signals"]]
        assert "status_regressed" not in types


# ---------------------------------------------------------------------------
# E. Status improved — aborted → ok (no regression)
# ---------------------------------------------------------------------------

class TestStatusImproved:
    def test_aborted_to_ok_no_regression(self, tmp_path):
        # Previous=aborted, current=ok → improvement, no regression signal.
        cycle_ok_late = {
            **_CYCLE_OK_A,
            "timestamp": _TS_LATE,
            "selected_tasks": None,   # same task set as aborted (None) to isolate
        }
        _, data = _run(tmp_path, [_CYCLE_ABORTED_EARLY, cycle_ok_late])
        types = [s["type"] for s in data["signals"]]
        assert "status_regressed" not in types

    def test_aborted_to_ok_regression_detected_false(self, tmp_path):
        cycle_ok_late = {
            **_CYCLE_OK_A,
            "timestamp": _TS_LATE,
            "selected_tasks": None,
        }
        _, data = _run(tmp_path, [_CYCLE_ABORTED_EARLY, cycle_ok_late])
        assert data["regression_detected"] is False


# ---------------------------------------------------------------------------
# F. Both signals present simultaneously
# ---------------------------------------------------------------------------

class TestBothSignals:
    def test_both_signals_detected(self, tmp_path):
        # Previous: ok with tasks. Current: aborted with different (None) tasks.
        _, data = _run(tmp_path, [_CYCLE_OK_A, _CYCLE_ABORTED])
        types = [s["type"] for s in data["signals"]]
        assert "action_set_changed" in types
        assert "status_regressed" in types

    def test_signals_ordered_alphabetically(self, tmp_path):
        _, data = _run(tmp_path, [_CYCLE_OK_A, _CYCLE_ABORTED])
        types = [s["type"] for s in data["signals"]]
        assert types == sorted(types)

    def test_action_set_changed_before_status_regressed(self, tmp_path):
        _, data = _run(tmp_path, [_CYCLE_OK_A, _CYCLE_ABORTED])
        types = [s["type"] for s in data["signals"]]
        assert types.index("action_set_changed") < types.index("status_regressed")

    def test_regression_detected_true_with_both_signals(self, tmp_path):
        _, data = _run(tmp_path, [_CYCLE_OK_A, _CYCLE_ABORTED])
        assert data["regression_detected"] is True


# ---------------------------------------------------------------------------
# G. Deterministic output formatting
# ---------------------------------------------------------------------------

class TestDeterministicOutput:
    def test_trailing_newline(self, tmp_path):
        h = _write_history(tmp_path, [_CYCLE_OK_A, _CYCLE_OK_B])
        s = _write_summary(tmp_path)
        out = tmp_path / "regression.json"
        detect_cycle_history_regression(str(h), str(s), str(out))
        assert out.read_text(encoding="utf-8").endswith("\n")

    def test_sort_keys_alphabetical(self, tmp_path):
        h = _write_history(tmp_path, [_CYCLE_OK_A, _CYCLE_OK_B])
        s = _write_summary(tmp_path)
        out = tmp_path / "regression.json"
        detect_cycle_history_regression(str(h), str(s), str(out))
        raw = out.read_text(encoding="utf-8")
        data = json.loads(raw)
        expected = json.dumps(data, indent=2, sort_keys=True) + "\n"
        assert raw == expected

    def test_same_input_same_output(self, tmp_path):
        h = _write_history(tmp_path, [_CYCLE_OK_A, _CYCLE_OK_B])
        s = _write_summary(tmp_path)
        out1 = tmp_path / "r1.json"
        out2 = tmp_path / "r2.json"
        detect_cycle_history_regression(str(h), str(s), str(out1))
        detect_cycle_history_regression(str(h), str(s), str(out2))
        assert out1.read_text(encoding="utf-8") == out2.read_text(encoding="utf-8")

    def test_all_required_top_level_fields_present(self, tmp_path):
        _, data = _run(tmp_path, [_CYCLE_OK_A, _CYCLE_OK_B])
        required = {
            "current_cycle_timestamp",
            "insufficient_history",
            "regression_detected",
            "signals",
            "summary_context",
        }
        assert required <= set(data.keys())

    def test_creates_parent_dirs(self, tmp_path):
        h = _write_history(tmp_path, [_CYCLE_OK_A, _CYCLE_OK_B])
        s = _write_summary(tmp_path)
        out = tmp_path / "sub" / "nested" / "regression.json"
        rc = detect_cycle_history_regression(str(h), str(s), str(out))
        assert rc == 0
        assert out.exists()

    def test_insertion_order_does_not_affect_regression_result(self, tmp_path):
        """Cycle ordering in history file must not change detection result."""
        # Regardless of whether cycles appear early-then-late or late-then-early,
        # the detector uses timestamp sorting to find current/previous.
        h1 = _write_history(tmp_path, [_CYCLE_OK_A, _CYCLE_OK_DIFFERENT_TASKS], "h1.json")
        h2 = _write_history(tmp_path, [_CYCLE_OK_DIFFERENT_TASKS, _CYCLE_OK_A], "h2.json")
        s = _write_summary(tmp_path)
        out1 = tmp_path / "r1.json"
        out2 = tmp_path / "r2.json"
        detect_cycle_history_regression(str(h1), str(s), str(out1))
        detect_cycle_history_regression(str(h2), str(s), str(out2))
        d1 = json.loads(out1.read_text())
        d2 = json.loads(out2.read_text())
        assert d1["regression_detected"] == d2["regression_detected"]
        assert d1["signals"] == d2["signals"]


# ---------------------------------------------------------------------------
# H. Invalid history file handling
# ---------------------------------------------------------------------------

class TestInvalidHistory:
    def test_missing_history_returns_one(self, tmp_path):
        s = _write_summary(tmp_path)
        out = tmp_path / "regression.json"
        rc = detect_cycle_history_regression(
            str(tmp_path / "nonexistent.json"), str(s), str(out)
        )
        assert rc == 1

    def test_missing_history_no_output_created(self, tmp_path):
        s = _write_summary(tmp_path)
        out = tmp_path / "regression.json"
        detect_cycle_history_regression(
            str(tmp_path / "nonexistent.json"), str(s), str(out)
        )
        assert not out.exists()

    def test_bad_json_history_returns_one(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("not json{{", encoding="utf-8")
        s = _write_summary(tmp_path)
        out = tmp_path / "regression.json"
        rc = detect_cycle_history_regression(str(bad), str(s), str(out))
        assert rc == 1

    def test_history_root_is_list_returns_one(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text(json.dumps([]) + "\n", encoding="utf-8")
        s = _write_summary(tmp_path)
        out = tmp_path / "regression.json"
        rc = detect_cycle_history_regression(str(bad), str(s), str(out))
        assert rc == 1

    def test_history_missing_cycles_key_returns_one(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text(json.dumps({"records": []}) + "\n", encoding="utf-8")
        s = _write_summary(tmp_path)
        out = tmp_path / "regression.json"
        rc = detect_cycle_history_regression(str(bad), str(s), str(out))
        assert rc == 1

    def test_history_cycles_not_list_returns_one(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text(json.dumps({"cycles": "not-a-list"}) + "\n", encoding="utf-8")
        s = _write_summary(tmp_path)
        out = tmp_path / "regression.json"
        rc = detect_cycle_history_regression(str(bad), str(s), str(out))
        assert rc == 1


# ---------------------------------------------------------------------------
# I. Invalid summary file handling
# ---------------------------------------------------------------------------

class TestInvalidSummary:
    def test_missing_summary_returns_one(self, tmp_path):
        h = _write_history(tmp_path, [_CYCLE_OK_A, _CYCLE_OK_B])
        out = tmp_path / "regression.json"
        rc = detect_cycle_history_regression(
            str(h), str(tmp_path / "nonexistent.json"), str(out)
        )
        assert rc == 1

    def test_missing_summary_no_output_created(self, tmp_path):
        h = _write_history(tmp_path, [_CYCLE_OK_A, _CYCLE_OK_B])
        out = tmp_path / "regression.json"
        detect_cycle_history_regression(
            str(h), str(tmp_path / "nonexistent.json"), str(out)
        )
        assert not out.exists()

    def test_bad_json_summary_returns_one(self, tmp_path):
        h = _write_history(tmp_path, [_CYCLE_OK_A, _CYCLE_OK_B])
        bad = tmp_path / "bad_summary.json"
        bad.write_text("not json{{", encoding="utf-8")
        out = tmp_path / "regression.json"
        rc = detect_cycle_history_regression(str(h), str(bad), str(out))
        assert rc == 1

    def test_summary_root_is_list_returns_one(self, tmp_path):
        h = _write_history(tmp_path, [_CYCLE_OK_A, _CYCLE_OK_B])
        bad = tmp_path / "bad_summary.json"
        bad.write_text(json.dumps([]) + "\n", encoding="utf-8")
        out = tmp_path / "regression.json"
        rc = detect_cycle_history_regression(str(h), str(bad), str(out))
        assert rc == 1


# ---------------------------------------------------------------------------
# J. Invalid schema — combined
# ---------------------------------------------------------------------------

class TestInvalidSchema:
    def test_history_cycles_is_null_returns_one(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text(json.dumps({"cycles": None}) + "\n", encoding="utf-8")
        s = _write_summary(tmp_path)
        out = tmp_path / "regression.json"
        rc = detect_cycle_history_regression(str(bad), str(s), str(out))
        assert rc == 1

    def test_valid_empty_cycles_succeeds(self, tmp_path):
        h = _write_history(tmp_path, [])
        s = _write_summary(tmp_path)
        out = tmp_path / "regression.json"
        rc = detect_cycle_history_regression(str(h), str(s), str(out))
        assert rc == 0


# ---------------------------------------------------------------------------
# K. Summary context pass-through
# ---------------------------------------------------------------------------

class TestSummaryContext:
    def test_summary_context_present_in_report(self, tmp_path):
        _, data = _run(tmp_path, [_CYCLE_OK_A, _CYCLE_OK_B])
        assert "summary_context" in data

    def test_summary_context_cycles_total(self, tmp_path):
        _, data = _run(tmp_path, [_CYCLE_OK_A, _CYCLE_OK_B])
        assert data["summary_context"]["cycles_total"] == _SUMMARY_OK["cycles_total"]

    def test_summary_context_success_rate(self, tmp_path):
        _, data = _run(tmp_path, [_CYCLE_OK_A, _CYCLE_OK_B])
        assert data["summary_context"]["success_rate"] == _SUMMARY_OK["success_rate"]

    def test_summary_context_unique_tasks(self, tmp_path):
        _, data = _run(tmp_path, [_CYCLE_OK_A, _CYCLE_OK_B])
        assert data["summary_context"]["unique_tasks_selected"] == (
            _SUMMARY_OK["unique_tasks_selected"]
        )

    def test_summary_context_with_mismatched_cycles_total(self, tmp_path):
        """History is source of truth for detection; summary context is passed through as-is."""
        # history has 2 cycles, summary says 99 — detector uses history for detection
        # but still includes the summary's cycles_total in context
        mismatched_summary = {**_SUMMARY_OK, "cycles_total": 99}
        h = _write_history(tmp_path, [_CYCLE_OK_A, _CYCLE_OK_B])
        s = _write_summary(tmp_path, mismatched_summary)
        out = tmp_path / "regression.json"
        detect_cycle_history_regression(str(h), str(s), str(out))
        data = json.loads(out.read_text())
        assert data["summary_context"]["cycles_total"] == 99
        # Detection still correctly uses the 2 cycles from history
        assert data["insufficient_history"] is False

    def test_summary_context_three_required_fields(self, tmp_path):
        _, data = _run(tmp_path, [_CYCLE_OK_A, _CYCLE_OK_B])
        ctx = data["summary_context"]
        assert "cycles_total" in ctx
        assert "success_rate" in ctx
        assert "unique_tasks_selected" in ctx


# ---------------------------------------------------------------------------
# L. _detect_signals unit tests (pure function)
# ---------------------------------------------------------------------------

class TestDetectSignalsUnit:
    def test_identical_records_no_signals(self):
        assert _detect_signals(_CYCLE_OK_A, _CYCLE_OK_B) == []

    def test_action_set_changed_signal(self):
        signals = _detect_signals(_CYCLE_OK_A, _CYCLE_OK_DIFFERENT_TASKS)
        types = [s["type"] for s in signals]
        assert "action_set_changed" in types

    def test_status_regressed_signal(self):
        signals = _detect_signals(_CYCLE_OK_A, _CYCLE_ABORTED)
        types = [s["type"] for s in signals]
        assert "status_regressed" in types

    def test_no_status_regression_on_improvement(self):
        signals = _detect_signals(_CYCLE_ABORTED_EARLY, _CYCLE_OK_A)
        types = [s["type"] for s in signals]
        assert "status_regressed" not in types

    def test_signals_sorted_by_type(self):
        signals = _detect_signals(_CYCLE_OK_A, _CYCLE_ABORTED)
        types = [s["type"] for s in signals]
        assert types == sorted(types)

    def test_same_status_aborted_no_status_signal(self):
        cycle_aborted_late = {**_CYCLE_ABORTED_EARLY, "timestamp": _TS_LATE}
        signals = _detect_signals(_CYCLE_ABORTED_EARLY, cycle_aborted_late)
        types = [s["type"] for s in signals]
        assert "status_regressed" not in types

    def test_empty_vs_none_tasks_no_action_signal(self):
        prev = {"selected_tasks": None, "status": "ok"}
        curr = {"selected_tasks": [], "status": "ok"}
        signals = _detect_signals(prev, curr)
        types = [s["type"] for s in signals]
        assert "action_set_changed" not in types

    def test_action_signal_uses_sorted_lists(self):
        prev = {"selected_tasks": ["z_task", "a_task"], "status": "ok"}
        curr = {"selected_tasks": ["b_task"], "status": "ok"}
        signals = _detect_signals(prev, curr)
        sig = next(s for s in signals if s["type"] == "action_set_changed")
        assert sig["previous_selected_tasks"] == ["a_task", "z_task"]
        assert sig["current_selected_tasks"] == ["b_task"]


# ---------------------------------------------------------------------------
# M. _status_rank unit tests
# ---------------------------------------------------------------------------

class TestStatusRank:
    def test_ok_rank_higher_than_aborted(self):
        assert _status_rank("ok") > _status_rank("aborted")

    def test_unknown_status_treated_as_worst(self):
        assert _status_rank("unknown_status") == _status_rank("aborted")

    def test_ok_rank_is_positive(self):
        assert _status_rank("ok") > 0

    def test_aborted_rank_is_zero(self):
        assert _status_rank("aborted") == 0
