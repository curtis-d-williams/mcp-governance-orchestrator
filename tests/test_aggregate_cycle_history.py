# SPDX-License-Identifier: MIT
"""Tests for scripts/aggregate_cycle_history.py (Phase J).

Covers:
A. Empty history — zero-count summary, deterministic shape.
B. Single-cycle — all counters populate correctly.
C. Multi-cycle — status, ledger source, task frequency, timestamps.
D. Status aggregation — ok/aborted counts, success_rate.
E. Ledger source aggregation — counts per source.
F. Task selection frequency — per-task counts, unique count.
G. Most-recent timestamp selection.
H. Deterministic output formatting.
I. Invalid file handling — missing file, bad JSON, wrong schema.
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

_SCRIPT = _REPO_ROOT / "scripts" / "aggregate_cycle_history.py"
_spec = importlib.util.spec_from_file_location("aggregate_cycle_history", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

aggregate_cycle_history = _mod.aggregate_cycle_history
_compute_summary = _mod._compute_summary

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_TS_EARLY = "2026-01-01T10:00:00.000000Z"
_TS_MID   = "2026-03-10T20:42:52.576291Z"
_TS_LATE  = "2026-03-10T20:43:46.008272Z"

_CYCLE_OK = {
    "ledger_source": "work_dir",
    "selected_tasks": ["artifact_audit_example", "build_portfolio_dashboard"],
    "status": "ok",
    "timestamp": _TS_MID,
}

_CYCLE_OK_2 = {
    "ledger_source": "work_dir",
    "selected_tasks": ["artifact_audit_example", "failure_recovery_example"],
    "status": "ok",
    "timestamp": _TS_LATE,
}

_CYCLE_ABORTED = {
    "ledger_source": "none",
    "selected_tasks": None,
    "status": "aborted",
    "timestamp": _TS_EARLY,
}

_CYCLE_EXPLICIT_LEDGER = {
    "ledger_source": "explicit",
    "selected_tasks": ["build_portfolio_dashboard"],
    "status": "ok",
    "timestamp": _TS_MID,
}


def _write_history(tmp_path, cycles, name="cycle_history.json"):
    p = tmp_path / name
    p.write_text(json.dumps({"cycles": cycles}, indent=2) + "\n", encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# A. Empty history
# ---------------------------------------------------------------------------

class TestEmptyHistory:
    def test_returns_zero(self, tmp_path):
        h = _write_history(tmp_path, [])
        out = tmp_path / "summary.json"
        rc = aggregate_cycle_history(str(h), str(out))
        assert rc == 0

    def test_creates_output_file(self, tmp_path):
        h = _write_history(tmp_path, [])
        out = tmp_path / "summary.json"
        aggregate_cycle_history(str(h), str(out))
        assert out.exists()

    def test_output_valid_json(self, tmp_path):
        h = _write_history(tmp_path, [])
        out = tmp_path / "summary.json"
        aggregate_cycle_history(str(h), str(out))
        data = json.loads(out.read_text())
        assert isinstance(data, dict)

    def test_cycles_total_zero(self, tmp_path):
        h = _write_history(tmp_path, [])
        out = tmp_path / "summary.json"
        aggregate_cycle_history(str(h), str(out))
        data = json.loads(out.read_text())
        assert data["cycles_total"] == 0

    def test_status_counts_empty_dict(self, tmp_path):
        h = _write_history(tmp_path, [])
        out = tmp_path / "summary.json"
        aggregate_cycle_history(str(h), str(out))
        data = json.loads(out.read_text())
        assert data["status_counts"] == {}

    def test_ledger_source_counts_empty_dict(self, tmp_path):
        h = _write_history(tmp_path, [])
        out = tmp_path / "summary.json"
        aggregate_cycle_history(str(h), str(out))
        data = json.loads(out.read_text())
        assert data["ledger_source_counts"] == {}

    def test_task_selection_counts_empty_dict(self, tmp_path):
        h = _write_history(tmp_path, [])
        out = tmp_path / "summary.json"
        aggregate_cycle_history(str(h), str(out))
        data = json.loads(out.read_text())
        assert data["task_selection_counts"] == {}

    def test_unique_tasks_selected_zero(self, tmp_path):
        h = _write_history(tmp_path, [])
        out = tmp_path / "summary.json"
        aggregate_cycle_history(str(h), str(out))
        data = json.loads(out.read_text())
        assert data["unique_tasks_selected"] == 0

    def test_most_recent_timestamp_none(self, tmp_path):
        h = _write_history(tmp_path, [])
        out = tmp_path / "summary.json"
        aggregate_cycle_history(str(h), str(out))
        data = json.loads(out.read_text())
        assert data["most_recent_cycle_timestamp"] is None

    def test_success_rate_none(self, tmp_path):
        h = _write_history(tmp_path, [])
        out = tmp_path / "summary.json"
        aggregate_cycle_history(str(h), str(out))
        data = json.loads(out.read_text())
        assert data["success_rate"] is None

    def test_average_tasks_zero(self, tmp_path):
        h = _write_history(tmp_path, [])
        out = tmp_path / "summary.json"
        aggregate_cycle_history(str(h), str(out))
        data = json.loads(out.read_text())
        assert data["average_tasks_selected_per_cycle"] == 0.0

    def test_cycles_with_selected_tasks_zero(self, tmp_path):
        h = _write_history(tmp_path, [])
        out = tmp_path / "summary.json"
        aggregate_cycle_history(str(h), str(out))
        data = json.loads(out.read_text())
        assert data["cycles_with_selected_tasks"] == 0


# ---------------------------------------------------------------------------
# B. Single-cycle
# ---------------------------------------------------------------------------

class TestSingleCycle:
    def _run(self, tmp_path, cycle=None):
        h = _write_history(tmp_path, [cycle or _CYCLE_OK])
        out = tmp_path / "summary.json"
        aggregate_cycle_history(str(h), str(out))
        return json.loads(out.read_text())

    def test_cycles_total_one(self, tmp_path):
        data = self._run(tmp_path)
        assert data["cycles_total"] == 1

    def test_status_counts_ok_one(self, tmp_path):
        data = self._run(tmp_path)
        assert data["status_counts"] == {"ok": 1}

    def test_ledger_source_counts_work_dir_one(self, tmp_path):
        data = self._run(tmp_path)
        assert data["ledger_source_counts"] == {"work_dir": 1}

    def test_task_selection_counts_correct(self, tmp_path):
        data = self._run(tmp_path)
        assert data["task_selection_counts"] == {
            "artifact_audit_example": 1,
            "build_portfolio_dashboard": 1,
        }

    def test_unique_tasks_selected_two(self, tmp_path):
        data = self._run(tmp_path)
        assert data["unique_tasks_selected"] == 2

    def test_most_recent_timestamp(self, tmp_path):
        data = self._run(tmp_path)
        assert data["most_recent_cycle_timestamp"] == _TS_MID

    def test_success_rate_one_point_zero(self, tmp_path):
        data = self._run(tmp_path)
        assert data["success_rate"] == 1.0

    def test_average_tasks_per_cycle(self, tmp_path):
        data = self._run(tmp_path)
        # _CYCLE_OK has 2 selected_tasks, 1 cycle → 2.0
        assert data["average_tasks_selected_per_cycle"] == 2.0

    def test_cycles_with_selected_tasks_one(self, tmp_path):
        data = self._run(tmp_path)
        assert data["cycles_with_selected_tasks"] == 1

    def test_aborted_cycle_success_rate_zero(self, tmp_path):
        data = self._run(tmp_path, cycle=_CYCLE_ABORTED)
        assert data["success_rate"] == 0.0

    def test_aborted_cycle_status_counts(self, tmp_path):
        data = self._run(tmp_path, cycle=_CYCLE_ABORTED)
        assert data["status_counts"] == {"aborted": 1}

    def test_none_selected_tasks_not_counted(self, tmp_path):
        data = self._run(tmp_path, cycle=_CYCLE_ABORTED)
        assert data["task_selection_counts"] == {}
        assert data["cycles_with_selected_tasks"] == 0
        assert data["average_tasks_selected_per_cycle"] == 0.0


# ---------------------------------------------------------------------------
# C. Multi-cycle counts
# ---------------------------------------------------------------------------

class TestMultiCycle:
    def _run(self, tmp_path, cycles):
        h = _write_history(tmp_path, cycles)
        out = tmp_path / "summary.json"
        aggregate_cycle_history(str(h), str(out))
        return json.loads(out.read_text())

    def test_cycles_total_two(self, tmp_path):
        data = self._run(tmp_path, [_CYCLE_OK, _CYCLE_OK_2])
        assert data["cycles_total"] == 2

    def test_cycles_total_three(self, tmp_path):
        data = self._run(tmp_path, [_CYCLE_OK, _CYCLE_OK_2, _CYCLE_ABORTED])
        assert data["cycles_total"] == 3

    def test_task_counts_accumulate(self, tmp_path):
        data = self._run(tmp_path, [_CYCLE_OK, _CYCLE_OK_2])
        # _CYCLE_OK: artifact_audit_example, build_portfolio_dashboard
        # _CYCLE_OK_2: artifact_audit_example, failure_recovery_example
        assert data["task_selection_counts"]["artifact_audit_example"] == 2
        assert data["task_selection_counts"]["build_portfolio_dashboard"] == 1
        assert data["task_selection_counts"]["failure_recovery_example"] == 1

    def test_unique_tasks_selected_three(self, tmp_path):
        data = self._run(tmp_path, [_CYCLE_OK, _CYCLE_OK_2])
        # artifact_audit_example, build_portfolio_dashboard, failure_recovery_example
        assert data["unique_tasks_selected"] == 3

    def test_cycles_with_selected_tasks_two(self, tmp_path):
        data = self._run(tmp_path, [_CYCLE_OK, _CYCLE_OK_2])
        assert data["cycles_with_selected_tasks"] == 2

    def test_cycles_with_tasks_excludes_aborted_no_tasks(self, tmp_path):
        data = self._run(tmp_path, [_CYCLE_OK, _CYCLE_ABORTED])
        assert data["cycles_with_selected_tasks"] == 1


# ---------------------------------------------------------------------------
# D. Status aggregation
# ---------------------------------------------------------------------------

class TestStatusAggregation:
    def test_two_ok_cycles(self, tmp_path):
        h = _write_history(tmp_path, [_CYCLE_OK, _CYCLE_OK_2])
        out = tmp_path / "summary.json"
        aggregate_cycle_history(str(h), str(out))
        data = json.loads(out.read_text())
        assert data["status_counts"] == {"ok": 2}

    def test_mixed_statuses(self, tmp_path):
        h = _write_history(tmp_path, [_CYCLE_OK, _CYCLE_ABORTED])
        out = tmp_path / "summary.json"
        aggregate_cycle_history(str(h), str(out))
        data = json.loads(out.read_text())
        assert data["status_counts"] == {"aborted": 1, "ok": 1}

    def test_success_rate_one_of_two(self, tmp_path):
        h = _write_history(tmp_path, [_CYCLE_OK, _CYCLE_ABORTED])
        out = tmp_path / "summary.json"
        aggregate_cycle_history(str(h), str(out))
        data = json.loads(out.read_text())
        assert data["success_rate"] == 0.5

    def test_success_rate_two_of_two(self, tmp_path):
        h = _write_history(tmp_path, [_CYCLE_OK, _CYCLE_OK_2])
        out = tmp_path / "summary.json"
        aggregate_cycle_history(str(h), str(out))
        data = json.loads(out.read_text())
        assert data["success_rate"] == 1.0

    def test_null_status_not_counted(self, tmp_path):
        cycle_no_status = {
            "ledger_source": "work_dir",
            "selected_tasks": ["task_a"],
            "status": None,
            "timestamp": _TS_MID,
        }
        h = _write_history(tmp_path, [cycle_no_status])
        out = tmp_path / "summary.json"
        aggregate_cycle_history(str(h), str(out))
        data = json.loads(out.read_text())
        assert data["status_counts"] == {}


# ---------------------------------------------------------------------------
# E. Ledger source aggregation
# ---------------------------------------------------------------------------

class TestLedgerSourceAggregation:
    def test_two_work_dir(self, tmp_path):
        h = _write_history(tmp_path, [_CYCLE_OK, _CYCLE_OK_2])
        out = tmp_path / "summary.json"
        aggregate_cycle_history(str(h), str(out))
        data = json.loads(out.read_text())
        assert data["ledger_source_counts"] == {"work_dir": 2}

    def test_mixed_sources(self, tmp_path):
        h = _write_history(tmp_path, [_CYCLE_OK, _CYCLE_EXPLICIT_LEDGER, _CYCLE_ABORTED])
        out = tmp_path / "summary.json"
        aggregate_cycle_history(str(h), str(out))
        data = json.loads(out.read_text())
        assert data["ledger_source_counts"] == {
            "explicit": 1,
            "none": 1,
            "work_dir": 1,
        }

    def test_null_ledger_source_not_counted(self, tmp_path):
        cycle = {
            "ledger_source": None,
            "selected_tasks": ["task_a"],
            "status": "ok",
            "timestamp": _TS_MID,
        }
        h = _write_history(tmp_path, [cycle])
        out = tmp_path / "summary.json"
        aggregate_cycle_history(str(h), str(out))
        data = json.loads(out.read_text())
        assert data["ledger_source_counts"] == {}


# ---------------------------------------------------------------------------
# F. Task selection frequency
# ---------------------------------------------------------------------------

class TestTaskSelectionFrequency:
    def test_single_task_appears_once(self, tmp_path):
        h = _write_history(tmp_path, [_CYCLE_EXPLICIT_LEDGER])
        out = tmp_path / "summary.json"
        aggregate_cycle_history(str(h), str(out))
        data = json.loads(out.read_text())
        assert data["task_selection_counts"] == {"build_portfolio_dashboard": 1}

    def test_task_appearing_in_every_cycle_counts_correctly(self, tmp_path):
        h = _write_history(tmp_path, [_CYCLE_OK, _CYCLE_OK_2])
        out = tmp_path / "summary.json"
        aggregate_cycle_history(str(h), str(out))
        data = json.loads(out.read_text())
        assert data["task_selection_counts"]["artifact_audit_example"] == 2

    def test_unique_tasks_reflects_distinct_task_names(self, tmp_path):
        cycle_all = {
            "ledger_source": "work_dir",
            "selected_tasks": ["a", "b", "c", "d", "e"],
            "status": "ok",
            "timestamp": _TS_MID,
        }
        h = _write_history(tmp_path, [cycle_all])
        out = tmp_path / "summary.json"
        aggregate_cycle_history(str(h), str(out))
        data = json.loads(out.read_text())
        assert data["unique_tasks_selected"] == 5

    def test_average_tasks_two_cycles_four_tasks(self, tmp_path):
        # _CYCLE_OK: 2 tasks, _CYCLE_OK_2: 2 tasks → avg = 2.0
        h = _write_history(tmp_path, [_CYCLE_OK, _CYCLE_OK_2])
        out = tmp_path / "summary.json"
        aggregate_cycle_history(str(h), str(out))
        data = json.loads(out.read_text())
        assert data["average_tasks_selected_per_cycle"] == 2.0

    def test_average_tasks_with_empty_cycle(self, tmp_path):
        # 1 cycle with 2 tasks + 1 aborted (0 tasks) → avg = 1.0
        h = _write_history(tmp_path, [_CYCLE_OK, _CYCLE_ABORTED])
        out = tmp_path / "summary.json"
        aggregate_cycle_history(str(h), str(out))
        data = json.loads(out.read_text())
        assert data["average_tasks_selected_per_cycle"] == 1.0

    def test_empty_selected_tasks_list_not_counted(self, tmp_path):
        cycle_empty_tasks = {
            "ledger_source": "work_dir",
            "selected_tasks": [],
            "status": "ok",
            "timestamp": _TS_MID,
        }
        h = _write_history(tmp_path, [cycle_empty_tasks])
        out = tmp_path / "summary.json"
        aggregate_cycle_history(str(h), str(out))
        data = json.loads(out.read_text())
        assert data["cycles_with_selected_tasks"] == 0
        assert data["task_selection_counts"] == {}


# ---------------------------------------------------------------------------
# G. Most-recent timestamp
# ---------------------------------------------------------------------------

class TestMostRecentTimestamp:
    def test_single_cycle_timestamp(self, tmp_path):
        h = _write_history(tmp_path, [_CYCLE_OK])
        out = tmp_path / "summary.json"
        aggregate_cycle_history(str(h), str(out))
        data = json.loads(out.read_text())
        assert data["most_recent_cycle_timestamp"] == _TS_MID

    def test_most_recent_selected_from_multiple(self, tmp_path):
        h = _write_history(tmp_path, [_CYCLE_ABORTED, _CYCLE_OK, _CYCLE_OK_2])
        out = tmp_path / "summary.json"
        aggregate_cycle_history(str(h), str(out))
        data = json.loads(out.read_text())
        # _TS_LATE > _TS_MID > _TS_EARLY
        assert data["most_recent_cycle_timestamp"] == _TS_LATE

    def test_null_timestamp_skipped(self, tmp_path):
        cycle_no_ts = {
            "ledger_source": "work_dir",
            "selected_tasks": ["task_a"],
            "status": "ok",
            "timestamp": None,
        }
        cycle_with_ts = {
            "ledger_source": "work_dir",
            "selected_tasks": ["task_b"],
            "status": "ok",
            "timestamp": _TS_MID,
        }
        h = _write_history(tmp_path, [cycle_no_ts, cycle_with_ts])
        out = tmp_path / "summary.json"
        aggregate_cycle_history(str(h), str(out))
        data = json.loads(out.read_text())
        assert data["most_recent_cycle_timestamp"] == _TS_MID

    def test_all_null_timestamps_returns_none(self, tmp_path):
        cycle = {
            "ledger_source": "work_dir",
            "selected_tasks": ["task_a"],
            "status": "ok",
            "timestamp": None,
        }
        h = _write_history(tmp_path, [cycle])
        out = tmp_path / "summary.json"
        aggregate_cycle_history(str(h), str(out))
        data = json.loads(out.read_text())
        assert data["most_recent_cycle_timestamp"] is None


# ---------------------------------------------------------------------------
# H. Deterministic output formatting
# ---------------------------------------------------------------------------

class TestDeterministicOutput:
    def test_trailing_newline(self, tmp_path):
        h = _write_history(tmp_path, [_CYCLE_OK])
        out = tmp_path / "summary.json"
        aggregate_cycle_history(str(h), str(out))
        assert out.read_text(encoding="utf-8").endswith("\n")

    def test_sort_keys_alphabetical(self, tmp_path):
        h = _write_history(tmp_path, [_CYCLE_OK])
        out = tmp_path / "summary.json"
        aggregate_cycle_history(str(h), str(out))
        raw = out.read_text(encoding="utf-8")
        data = json.loads(raw)
        expected = json.dumps(data, indent=2, sort_keys=True) + "\n"
        assert raw == expected

    def test_same_input_same_output(self, tmp_path):
        cycles = [_CYCLE_OK, _CYCLE_OK_2, _CYCLE_ABORTED]
        h = _write_history(tmp_path, cycles)
        out1 = tmp_path / "summary1.json"
        out2 = tmp_path / "summary2.json"
        aggregate_cycle_history(str(h), str(out1))
        aggregate_cycle_history(str(h), str(out2))
        assert out1.read_text(encoding="utf-8") == out2.read_text(encoding="utf-8")

    def test_insertion_order_does_not_affect_output(self, tmp_path):
        """Output must be stable regardless of cycle insertion order."""
        h1 = _write_history(tmp_path, [_CYCLE_OK, _CYCLE_OK_2], "h1.json")
        h2 = _write_history(tmp_path, [_CYCLE_OK_2, _CYCLE_OK], "h2.json")
        out1 = tmp_path / "out1.json"
        out2 = tmp_path / "out2.json"
        aggregate_cycle_history(str(h1), str(out1))
        aggregate_cycle_history(str(h2), str(out2))
        assert out1.read_text(encoding="utf-8") == out2.read_text(encoding="utf-8")

    def test_all_required_fields_present(self, tmp_path):
        h = _write_history(tmp_path, [_CYCLE_OK])
        out = tmp_path / "summary.json"
        aggregate_cycle_history(str(h), str(out))
        data = json.loads(out.read_text())
        required = {
            "average_tasks_selected_per_cycle",
            "cycles_total",
            "cycles_with_selected_tasks",
            "ledger_source_counts",
            "most_recent_cycle_timestamp",
            "status_counts",
            "success_rate",
            "task_selection_counts",
            "unique_tasks_selected",
        }
        assert required <= set(data.keys())

    def test_creates_parent_dirs(self, tmp_path):
        h = _write_history(tmp_path, [_CYCLE_OK])
        out = tmp_path / "subdir" / "nested" / "summary.json"
        rc = aggregate_cycle_history(str(h), str(out))
        assert rc == 0
        assert out.exists()


# ---------------------------------------------------------------------------
# I. Invalid file / schema handling
# ---------------------------------------------------------------------------

class TestInvalidInput:
    def test_missing_file_returns_one(self, tmp_path):
        out = tmp_path / "summary.json"
        rc = aggregate_cycle_history(
            str(tmp_path / "nonexistent.json"),
            str(out),
        )
        assert rc == 1

    def test_missing_file_no_output_created(self, tmp_path):
        out = tmp_path / "summary.json"
        aggregate_cycle_history(str(tmp_path / "nonexistent.json"), str(out))
        assert not out.exists()

    def test_bad_json_returns_one(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("not json{{", encoding="utf-8")
        out = tmp_path / "summary.json"
        rc = aggregate_cycle_history(str(bad), str(out))
        assert rc == 1

    def test_bad_json_no_output_created(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("not json", encoding="utf-8")
        out = tmp_path / "summary.json"
        aggregate_cycle_history(str(bad), str(out))
        assert not out.exists()

    def test_root_is_list_returns_one(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text(json.dumps([{"status": "ok"}]) + "\n", encoding="utf-8")
        out = tmp_path / "summary.json"
        rc = aggregate_cycle_history(str(bad), str(out))
        assert rc == 1

    def test_root_is_string_returns_one(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text(json.dumps("not a dict") + "\n", encoding="utf-8")
        out = tmp_path / "summary.json"
        rc = aggregate_cycle_history(str(bad), str(out))
        assert rc == 1

    def test_missing_cycles_key_returns_one(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text(json.dumps({"records": []}) + "\n", encoding="utf-8")
        out = tmp_path / "summary.json"
        rc = aggregate_cycle_history(str(bad), str(out))
        assert rc == 1

    def test_cycles_is_not_list_returns_one(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text(json.dumps({"cycles": "not-a-list"}) + "\n", encoding="utf-8")
        out = tmp_path / "summary.json"
        rc = aggregate_cycle_history(str(bad), str(out))
        assert rc == 1

    def test_cycles_is_null_returns_one(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text(json.dumps({"cycles": None}) + "\n", encoding="utf-8")
        out = tmp_path / "summary.json"
        rc = aggregate_cycle_history(str(bad), str(out))
        assert rc == 1

    def test_valid_empty_cycles_list_returns_zero(self, tmp_path):
        h = _write_history(tmp_path, [])
        out = tmp_path / "summary.json"
        rc = aggregate_cycle_history(str(h), str(out))
        assert rc == 0


# ---------------------------------------------------------------------------
# J. _compute_summary unit tests (pure function)
# ---------------------------------------------------------------------------

class TestComputeSummaryUnit:
    def test_empty_list_returns_zero_counts(self):
        result = _compute_summary([])
        assert result["cycles_total"] == 0
        assert result["success_rate"] is None
        assert result["most_recent_cycle_timestamp"] is None
        assert result["average_tasks_selected_per_cycle"] == 0.0

    def test_single_ok_cycle(self):
        result = _compute_summary([_CYCLE_OK])
        assert result["cycles_total"] == 1
        assert result["success_rate"] == 1.0
        assert result["status_counts"] == {"ok": 1}
        assert result["ledger_source_counts"] == {"work_dir": 1}
        assert result["unique_tasks_selected"] == 2

    def test_task_counts_stable_across_calls(self):
        r1 = _compute_summary([_CYCLE_OK, _CYCLE_OK_2])
        r2 = _compute_summary([_CYCLE_OK, _CYCLE_OK_2])
        assert r1 == r2

    def test_missing_selected_tasks_key_treated_as_empty(self):
        cycle = {"status": "ok", "ledger_source": "work_dir", "timestamp": _TS_MID}
        result = _compute_summary([cycle])
        assert result["unique_tasks_selected"] == 0
        assert result["task_selection_counts"] == {}
