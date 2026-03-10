# SPDX-License-Identifier: MIT
"""Tests for scripts/update_cycle_history.py.

Covers:
A. Record normalization — correct keys, values derived from cycle artifact.
B. File creation — creates history when absent, writes valid JSON.
C. Idempotency — same record (same timestamp) not duplicated.
D. Accumulation and ordering — distinct records appended, order stable.
E. Error cases — unreadable input, missing file.
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

_SCRIPT = _REPO_ROOT / "scripts" / "update_cycle_history.py"
_spec = importlib.util.spec_from_file_location("update_cycle_history", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

update_cycle_history = _mod.update_cycle_history
_normalize_record = _mod._normalize_record
_RECORD_KEYS = _mod._RECORD_KEYS

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_FIXED_TS = "2026-01-01T00:00:00Z"
_FIXED_TS_2 = "2026-01-02T00:00:00Z"

_CYCLE_ARTIFACT_OK = {
    "status": "ok",
    "planner_inputs": {
        "ledger_source": "work_dir",
        "ledger_path": "/tmp/action_effectiveness_ledger.json",
    },
    "execution_result": {
        "status": "ok",
        "selected_tasks": ["artifact_audit_example", "build_portfolio_dashboard"],
        "returncode": 0,
    },
}

_CYCLE_ARTIFACT_ABORTED = {
    "status": "aborted",
    "planner_inputs": {
        "ledger_source": "none",
        "ledger_path": None,
    },
    "execution_result": None,
}

_CYCLE_ARTIFACT_NO_PLANNER_INPUTS = {
    "status": "ok",
    "planner_inputs": None,
    "execution_result": {
        "selected_tasks": ["build_portfolio_dashboard"],
    },
}


def _write_cycle_artifact(tmp_path, data, name="governed_portfolio_cycle.json"):
    p = tmp_path / name
    p.write_text(json.dumps(data) + "\n", encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# A. Record normalization
# ---------------------------------------------------------------------------

class TestNormalizeRecord:
    def test_includes_all_record_keys(self):
        record = _normalize_record(_CYCLE_ARTIFACT_OK, _FIXED_TS)
        for k in _RECORD_KEYS:
            assert k in record

    def test_status_extracted(self):
        record = _normalize_record(_CYCLE_ARTIFACT_OK, _FIXED_TS)
        assert record["status"] == "ok"

    def test_ledger_source_extracted(self):
        record = _normalize_record(_CYCLE_ARTIFACT_OK, _FIXED_TS)
        assert record["ledger_source"] == "work_dir"

    def test_selected_tasks_extracted(self):
        record = _normalize_record(_CYCLE_ARTIFACT_OK, _FIXED_TS)
        assert record["selected_tasks"] == [
            "artifact_audit_example", "build_portfolio_dashboard"
        ]

    def test_timestamp_set(self):
        record = _normalize_record(_CYCLE_ARTIFACT_OK, _FIXED_TS)
        assert record["timestamp"] == _FIXED_TS

    def test_none_planner_inputs_yields_none_ledger_source(self):
        record = _normalize_record(_CYCLE_ARTIFACT_NO_PLANNER_INPUTS, _FIXED_TS)
        assert record["ledger_source"] is None

    def test_none_execution_result_yields_none_selected_tasks(self):
        record = _normalize_record(_CYCLE_ARTIFACT_ABORTED, _FIXED_TS)
        assert record["selected_tasks"] is None

    def test_aborted_artifact_status(self):
        record = _normalize_record(_CYCLE_ARTIFACT_ABORTED, _FIXED_TS)
        assert record["status"] == "aborted"

    def test_same_input_same_output(self):
        r1 = _normalize_record(_CYCLE_ARTIFACT_OK, _FIXED_TS)
        r2 = _normalize_record(_CYCLE_ARTIFACT_OK, _FIXED_TS)
        assert r1 == r2


# ---------------------------------------------------------------------------
# B. File creation
# ---------------------------------------------------------------------------

class TestFileCreation:
    def test_returns_zero_on_success(self, tmp_path):
        ca = _write_cycle_artifact(tmp_path, _CYCLE_ARTIFACT_OK)
        out = tmp_path / "cycle_history.json"
        rc = update_cycle_history(str(ca), str(out), _now_fn=lambda: _FIXED_TS)
        assert rc == 0

    def test_creates_output_file(self, tmp_path):
        ca = _write_cycle_artifact(tmp_path, _CYCLE_ARTIFACT_OK)
        out = tmp_path / "cycle_history.json"
        update_cycle_history(str(ca), str(out), _now_fn=lambda: _FIXED_TS)
        assert out.exists()

    def test_output_is_valid_json(self, tmp_path):
        ca = _write_cycle_artifact(tmp_path, _CYCLE_ARTIFACT_OK)
        out = tmp_path / "cycle_history.json"
        update_cycle_history(str(ca), str(out), _now_fn=lambda: _FIXED_TS)
        data = json.loads(out.read_text())
        assert isinstance(data, dict)

    def test_output_has_trailing_newline(self, tmp_path):
        ca = _write_cycle_artifact(tmp_path, _CYCLE_ARTIFACT_OK)
        out = tmp_path / "cycle_history.json"
        update_cycle_history(str(ca), str(out), _now_fn=lambda: _FIXED_TS)
        assert out.read_text(encoding="utf-8").endswith("\n")

    def test_output_has_cycles_list(self, tmp_path):
        ca = _write_cycle_artifact(tmp_path, _CYCLE_ARTIFACT_OK)
        out = tmp_path / "cycle_history.json"
        update_cycle_history(str(ca), str(out), _now_fn=lambda: _FIXED_TS)
        data = json.loads(out.read_text())
        assert isinstance(data["cycles"], list)

    def test_first_record_matches_normalized(self, tmp_path):
        ca = _write_cycle_artifact(tmp_path, _CYCLE_ARTIFACT_OK)
        out = tmp_path / "cycle_history.json"
        update_cycle_history(str(ca), str(out), _now_fn=lambda: _FIXED_TS)
        data = json.loads(out.read_text())
        assert len(data["cycles"]) == 1
        expected = _normalize_record(_CYCLE_ARTIFACT_OK, _FIXED_TS)
        assert data["cycles"][0] == expected

    def test_creates_parent_dirs(self, tmp_path):
        ca = _write_cycle_artifact(tmp_path, _CYCLE_ARTIFACT_OK)
        out = tmp_path / "subdir" / "nested" / "cycle_history.json"
        rc = update_cycle_history(str(ca), str(out), _now_fn=lambda: _FIXED_TS)
        assert rc == 0
        assert out.exists()


# ---------------------------------------------------------------------------
# C. Idempotency
# ---------------------------------------------------------------------------

class TestIdempotency:
    def test_second_run_returns_zero(self, tmp_path):
        ca = _write_cycle_artifact(tmp_path, _CYCLE_ARTIFACT_OK)
        out = tmp_path / "cycle_history.json"
        update_cycle_history(str(ca), str(out), _now_fn=lambda: _FIXED_TS)
        rc = update_cycle_history(str(ca), str(out), _now_fn=lambda: _FIXED_TS)
        assert rc == 0

    def test_same_record_not_duplicated(self, tmp_path):
        ca = _write_cycle_artifact(tmp_path, _CYCLE_ARTIFACT_OK)
        out = tmp_path / "cycle_history.json"
        update_cycle_history(str(ca), str(out), _now_fn=lambda: _FIXED_TS)
        update_cycle_history(str(ca), str(out), _now_fn=lambda: _FIXED_TS)
        data = json.loads(out.read_text())
        assert len(data["cycles"]) == 1

    def test_three_runs_same_timestamp_still_one_record(self, tmp_path):
        ca = _write_cycle_artifact(tmp_path, _CYCLE_ARTIFACT_OK)
        out = tmp_path / "cycle_history.json"
        for _ in range(3):
            update_cycle_history(str(ca), str(out), _now_fn=lambda: _FIXED_TS)
        data = json.loads(out.read_text())
        assert len(data["cycles"]) == 1

    def test_file_content_stable_across_runs(self, tmp_path):
        ca = _write_cycle_artifact(tmp_path, _CYCLE_ARTIFACT_OK)
        out = tmp_path / "cycle_history.json"
        update_cycle_history(str(ca), str(out), _now_fn=lambda: _FIXED_TS)
        text1 = out.read_text(encoding="utf-8")
        update_cycle_history(str(ca), str(out), _now_fn=lambda: _FIXED_TS)
        text2 = out.read_text(encoding="utf-8")
        assert text1 == text2

    def test_different_timestamp_adds_new_record(self, tmp_path):
        """Two calls with different timestamps on same artifact = two records."""
        ca = _write_cycle_artifact(tmp_path, _CYCLE_ARTIFACT_OK)
        out = tmp_path / "cycle_history.json"
        update_cycle_history(str(ca), str(out), _now_fn=lambda: _FIXED_TS)
        update_cycle_history(str(ca), str(out), _now_fn=lambda: _FIXED_TS_2)
        data = json.loads(out.read_text())
        assert len(data["cycles"]) == 2


# ---------------------------------------------------------------------------
# D. Accumulation and stable ordering
# ---------------------------------------------------------------------------

class TestAccumulation:
    def test_distinct_records_both_appended(self, tmp_path):
        ca_ok = _write_cycle_artifact(tmp_path, _CYCLE_ARTIFACT_OK, "ca_ok.json")
        ca_ab = _write_cycle_artifact(tmp_path, _CYCLE_ARTIFACT_ABORTED, "ca_ab.json")
        out = tmp_path / "cycle_history.json"
        update_cycle_history(str(ca_ok), str(out), _now_fn=lambda: _FIXED_TS)
        update_cycle_history(str(ca_ab), str(out), _now_fn=lambda: _FIXED_TS)
        data = json.loads(out.read_text())
        assert len(data["cycles"]) == 2

    def test_record_order_is_stable(self, tmp_path):
        ca_ok = _write_cycle_artifact(tmp_path, _CYCLE_ARTIFACT_OK, "ca_ok.json")
        ca_ab = _write_cycle_artifact(tmp_path, _CYCLE_ARTIFACT_ABORTED, "ca_ab.json")

        out1 = tmp_path / "history1.json"
        update_cycle_history(str(ca_ok), str(out1), _now_fn=lambda: _FIXED_TS)
        update_cycle_history(str(ca_ab), str(out1), _now_fn=lambda: _FIXED_TS)
        text_forward = out1.read_text(encoding="utf-8")

        out2 = tmp_path / "history2.json"
        update_cycle_history(str(ca_ab), str(out2), _now_fn=lambda: _FIXED_TS)
        update_cycle_history(str(ca_ok), str(out2), _now_fn=lambda: _FIXED_TS)
        text_reverse = out2.read_text(encoding="utf-8")

        assert text_forward == text_reverse

    def test_duplicate_mixed_with_new_keeps_correct_count(self, tmp_path):
        ca_ok = _write_cycle_artifact(tmp_path, _CYCLE_ARTIFACT_OK, "ca_ok.json")
        ca_ab = _write_cycle_artifact(tmp_path, _CYCLE_ARTIFACT_ABORTED, "ca_ab.json")
        out = tmp_path / "cycle_history.json"
        update_cycle_history(str(ca_ok), str(out), _now_fn=lambda: _FIXED_TS)
        update_cycle_history(str(ca_ok), str(out), _now_fn=lambda: _FIXED_TS)  # dup
        update_cycle_history(str(ca_ab), str(out), _now_fn=lambda: _FIXED_TS)  # new
        data = json.loads(out.read_text())
        assert len(data["cycles"]) == 2

    def test_output_sort_keys_deterministic(self, tmp_path):
        """JSON output uses sort_keys so field order is always alphabetical."""
        ca = _write_cycle_artifact(tmp_path, _CYCLE_ARTIFACT_OK)
        out = tmp_path / "cycle_history.json"
        update_cycle_history(str(ca), str(out), _now_fn=lambda: _FIXED_TS)
        raw = out.read_text(encoding="utf-8")
        data = json.loads(raw)
        # Re-serialise and compare — proves stable canonical form.
        expected = json.dumps(data, indent=2, sort_keys=True) + "\n"
        assert raw == expected

    def test_corrupt_existing_history_treated_as_empty(self, tmp_path):
        """If existing cycle_history.json is corrupt, start fresh."""
        ca = _write_cycle_artifact(tmp_path, _CYCLE_ARTIFACT_OK)
        out = tmp_path / "cycle_history.json"
        out.write_text("not json", encoding="utf-8")
        rc = update_cycle_history(str(ca), str(out), _now_fn=lambda: _FIXED_TS)
        assert rc == 0
        data = json.loads(out.read_text())
        assert len(data["cycles"]) == 1


# ---------------------------------------------------------------------------
# E. Error cases
# ---------------------------------------------------------------------------

class TestErrorCases:
    def test_returns_one_when_cycle_artifact_missing(self, tmp_path):
        out = tmp_path / "cycle_history.json"
        rc = update_cycle_history(
            str(tmp_path / "nonexistent.json"),
            str(out),
            _now_fn=lambda: _FIXED_TS,
        )
        assert rc == 1

    def test_returns_one_when_cycle_artifact_bad_json(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("not json", encoding="utf-8")
        out = tmp_path / "cycle_history.json"
        rc = update_cycle_history(str(bad), str(out), _now_fn=lambda: _FIXED_TS)
        assert rc == 1

    def test_output_not_created_on_error(self, tmp_path):
        out = tmp_path / "cycle_history.json"
        update_cycle_history(
            str(tmp_path / "nonexistent.json"),
            str(out),
            _now_fn=lambda: _FIXED_TS,
        )
        assert not out.exists()
