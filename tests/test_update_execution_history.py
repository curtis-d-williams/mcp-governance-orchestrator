# SPDX-License-Identifier: MIT
"""Tests for scripts/update_execution_history.py.

Covers:
A. Record normalization — correct keys selected, stable across re-runs.
B. History creation — creates file when absent, writes valid JSON.
C. Idempotency — rerunning with the same execution_result does not duplicate.
D. Accumulation — distinct records are appended and sorted deterministically.
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

_SCRIPT = _REPO_ROOT / "scripts" / "update_execution_history.py"
_spec = importlib.util.spec_from_file_location("update_execution_history", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

update_execution_history = _mod.update_execution_history
_normalize_record = _mod._normalize_record
_RECORD_KEYS = _mod._RECORD_KEYS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_EXEC_RESULT_OK = {
    "status": "ok",
    "selected_tasks": ["build_portfolio_dashboard"],
    "resolved_via": "selected_actions",
    "returncode": 0,
    "parsed_output": {"task_name": "build_portfolio_dashboard"},
    "stdout": "some output",
    "stderr": "",
}

_EXEC_RESULT_ABORTED = {
    "status": "aborted",
    "selected_tasks": [],
    "resolved_via": None,
    "returncode": 1,
    "parsed_output": None,
    "stdout": "",
    "stderr": "no tasks",
}


def _write_exec_result(tmp_path, data, name="execution_result.json"):
    p = tmp_path / name
    p.write_text(json.dumps(data) + "\n", encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# A. Record normalization
# ---------------------------------------------------------------------------

class TestNormalizeRecord:
    def test_includes_all_record_keys(self):
        record = _normalize_record(_EXEC_RESULT_OK)
        for k in _RECORD_KEYS:
            assert k in record

    def test_excludes_transient_fields(self):
        record = _normalize_record(_EXEC_RESULT_OK)
        assert "stdout" not in record
        assert "stderr" not in record

    def test_values_match_source(self):
        record = _normalize_record(_EXEC_RESULT_OK)
        assert record["status"] == "ok"
        assert record["returncode"] == 0
        assert record["selected_tasks"] == ["build_portfolio_dashboard"]
        assert record["resolved_via"] == "selected_actions"

    def test_missing_keys_become_none(self):
        record = _normalize_record({})
        for k in _RECORD_KEYS:
            assert record[k] is None

    def test_same_input_produces_same_record(self):
        r1 = _normalize_record(_EXEC_RESULT_OK)
        r2 = _normalize_record(_EXEC_RESULT_OK)
        assert r1 == r2


# ---------------------------------------------------------------------------
# B. History creation
# ---------------------------------------------------------------------------

class TestHistoryCreation:
    def test_returns_zero_on_success(self, tmp_path):
        er = _write_exec_result(tmp_path, _EXEC_RESULT_OK)
        out = tmp_path / "execution_history.json"
        rc = update_execution_history(str(er), str(out))
        assert rc == 0

    def test_creates_output_file(self, tmp_path):
        er = _write_exec_result(tmp_path, _EXEC_RESULT_OK)
        out = tmp_path / "execution_history.json"
        update_execution_history(str(er), str(out))
        assert out.exists()

    def test_output_is_valid_json(self, tmp_path):
        er = _write_exec_result(tmp_path, _EXEC_RESULT_OK)
        out = tmp_path / "execution_history.json"
        update_execution_history(str(er), str(out))
        data = json.loads(out.read_text())
        assert isinstance(data, dict)

    def test_output_has_trailing_newline(self, tmp_path):
        er = _write_exec_result(tmp_path, _EXEC_RESULT_OK)
        out = tmp_path / "execution_history.json"
        update_execution_history(str(er), str(out))
        assert out.read_text(encoding="utf-8").endswith("\n")

    def test_output_has_records_list(self, tmp_path):
        er = _write_exec_result(tmp_path, _EXEC_RESULT_OK)
        out = tmp_path / "execution_history.json"
        update_execution_history(str(er), str(out))
        data = json.loads(out.read_text())
        assert isinstance(data["records"], list)

    def test_first_record_matches_normalized(self, tmp_path):
        er = _write_exec_result(tmp_path, _EXEC_RESULT_OK)
        out = tmp_path / "execution_history.json"
        update_execution_history(str(er), str(out))
        data = json.loads(out.read_text())
        assert len(data["records"]) == 1
        expected = _normalize_record(_EXEC_RESULT_OK)
        assert data["records"][0] == expected

    def test_creates_parent_dirs(self, tmp_path):
        er = _write_exec_result(tmp_path, _EXEC_RESULT_OK)
        out = tmp_path / "subdir" / "execution_history.json"
        rc = update_execution_history(str(er), str(out))
        assert rc == 0
        assert out.exists()


# ---------------------------------------------------------------------------
# C. Idempotency
# ---------------------------------------------------------------------------

class TestIdempotency:
    def test_second_run_returns_zero(self, tmp_path):
        er = _write_exec_result(tmp_path, _EXEC_RESULT_OK)
        out = tmp_path / "execution_history.json"
        update_execution_history(str(er), str(out))
        rc = update_execution_history(str(er), str(out))
        assert rc == 0

    def test_same_record_not_duplicated(self, tmp_path):
        er = _write_exec_result(tmp_path, _EXEC_RESULT_OK)
        out = tmp_path / "execution_history.json"
        update_execution_history(str(er), str(out))
        update_execution_history(str(er), str(out))
        data = json.loads(out.read_text())
        assert len(data["records"]) == 1

    def test_three_runs_still_one_record(self, tmp_path):
        er = _write_exec_result(tmp_path, _EXEC_RESULT_OK)
        out = tmp_path / "execution_history.json"
        for _ in range(3):
            update_execution_history(str(er), str(out))
        data = json.loads(out.read_text())
        assert len(data["records"]) == 1

    def test_file_content_stable_across_runs(self, tmp_path):
        er = _write_exec_result(tmp_path, _EXEC_RESULT_OK)
        out = tmp_path / "execution_history.json"
        update_execution_history(str(er), str(out))
        text1 = out.read_text(encoding="utf-8")
        update_execution_history(str(er), str(out))
        text2 = out.read_text(encoding="utf-8")
        assert text1 == text2


# ---------------------------------------------------------------------------
# D. Accumulation and stable ordering
# ---------------------------------------------------------------------------

class TestAccumulation:
    def test_distinct_records_both_appended(self, tmp_path):
        er_ok = _write_exec_result(tmp_path, _EXEC_RESULT_OK, "er_ok.json")
        er_ab = _write_exec_result(tmp_path, _EXEC_RESULT_ABORTED, "er_aborted.json")
        out = tmp_path / "execution_history.json"
        update_execution_history(str(er_ok), str(out))
        update_execution_history(str(er_ab), str(out))
        data = json.loads(out.read_text())
        assert len(data["records"]) == 2

    def test_record_order_is_stable(self, tmp_path):
        er_ok = _write_exec_result(tmp_path, _EXEC_RESULT_OK, "er_ok.json")
        er_ab = _write_exec_result(tmp_path, _EXEC_RESULT_ABORTED, "er_aborted.json")
        out = tmp_path / "execution_history.json"
        # Insert in one order.
        update_execution_history(str(er_ok), str(out))
        update_execution_history(str(er_ab), str(out))
        text_forward = out.read_text(encoding="utf-8")

        out2 = tmp_path / "execution_history2.json"
        # Insert in reverse order.
        update_execution_history(str(er_ab), str(out2))
        update_execution_history(str(er_ok), str(out2))
        text_reverse = out2.read_text(encoding="utf-8")

        assert text_forward == text_reverse

    def test_duplicate_mixed_with_new_keeps_correct_count(self, tmp_path):
        er_ok = _write_exec_result(tmp_path, _EXEC_RESULT_OK, "er_ok.json")
        er_ab = _write_exec_result(tmp_path, _EXEC_RESULT_ABORTED, "er_aborted.json")
        out = tmp_path / "execution_history.json"
        update_execution_history(str(er_ok), str(out))
        update_execution_history(str(er_ok), str(out))   # duplicate
        update_execution_history(str(er_ab), str(out))   # new
        data = json.loads(out.read_text())
        assert len(data["records"]) == 2


# ---------------------------------------------------------------------------
# E. Error cases
# ---------------------------------------------------------------------------

class TestErrorCases:
    def test_returns_one_when_execution_result_missing(self, tmp_path):
        out = tmp_path / "execution_history.json"
        rc = update_execution_history(
            str(tmp_path / "nonexistent.json"),
            str(out),
        )
        assert rc == 1

    def test_returns_one_when_execution_result_bad_json(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("not json", encoding="utf-8")
        out = tmp_path / "execution_history.json"
        rc = update_execution_history(str(bad), str(out))
        assert rc == 1

    def test_existing_history_bad_json_treated_as_empty(self, tmp_path):
        """If existing history is corrupt, treat as empty and start fresh."""
        er = _write_exec_result(tmp_path, _EXEC_RESULT_OK)
        out = tmp_path / "execution_history.json"
        out.write_text("not json", encoding="utf-8")
        rc = update_execution_history(str(er), str(out))
        assert rc == 0
        data = json.loads(out.read_text())
        assert len(data["records"]) == 1
