# SPDX-License-Identifier: MIT
"""Tests for scripts/update_action_effectiveness_from_history.py.

Covers:
A. Aggregation logic — correct counts, last_status, sorting.
B. Ledger creation — file written, valid JSON, trailing newline.
C. Idempotency — repeated runs on the same history produce identical output.
D. Multi-record accumulation — counts accumulate correctly per task.
E. Non-ok status — increments failure_count, not success_count.
F. Error cases — unreadable history, invalid JSON, missing/non-list records.
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

_SCRIPT = _REPO_ROOT / "scripts" / "update_action_effectiveness_from_history.py"
_spec = importlib.util.spec_from_file_location(
    "update_action_effectiveness_from_history", _SCRIPT
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

update_action_effectiveness_from_history = _mod.update_action_effectiveness_from_history
_aggregate = _mod._aggregate


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _history(records):
    return {"records": records}


def _record(tasks, status="ok"):
    return {"selected_tasks": tasks, "status": status}


def _write_history(tmp_path, records, name="execution_history.json"):
    p = tmp_path / name
    p.write_text(json.dumps(_history(records)) + "\n", encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# A. Aggregation logic
# ---------------------------------------------------------------------------

class TestAggregateLogic:
    def test_single_ok_record(self):
        records = [_record(["build_portfolio_dashboard"], "ok")]
        actions = _aggregate(records)
        assert actions["build_portfolio_dashboard"] == {
            "failure_count": 0,
            "last_status": "ok",
            "success_count": 1,
            "total_runs": 1,
        }

    def test_single_aborted_record(self):
        records = [_record(["artifact_audit_example"], "aborted")]
        actions = _aggregate(records)
        assert actions["artifact_audit_example"]["success_count"] == 0
        assert actions["artifact_audit_example"]["failure_count"] == 1
        assert actions["artifact_audit_example"]["last_status"] == "aborted"

    def test_missing_status_treated_as_failure(self):
        records = [{"selected_tasks": ["repo_insights_example"]}]
        actions = _aggregate(records)
        assert actions["repo_insights_example"]["failure_count"] == 1
        assert actions["repo_insights_example"]["success_count"] == 0

    def test_missing_selected_tasks_skips_gracefully(self):
        records = [{"status": "ok"}]
        actions = _aggregate(records)
        assert actions == {}

    def test_none_selected_tasks_skips_gracefully(self):
        records = [{"selected_tasks": None, "status": "ok"}]
        actions = _aggregate(records)
        assert actions == {}

    def test_empty_selected_tasks_skips(self):
        records = [_record([], "ok")]
        actions = _aggregate(records)
        assert actions == {}

    def test_last_status_updated_to_most_recent(self):
        records = [
            _record(["build_portfolio_dashboard"], "ok"),
            _record(["build_portfolio_dashboard"], "aborted"),
        ]
        actions = _aggregate(records)
        assert actions["build_portfolio_dashboard"]["last_status"] == "aborted"

    def test_multiple_tasks_per_record(self):
        records = [_record(["task_a", "task_b"], "ok")]
        actions = _aggregate(records)
        assert actions["task_a"]["success_count"] == 1
        assert actions["task_b"]["success_count"] == 1

    def test_empty_records(self):
        assert _aggregate([]) == {}


# ---------------------------------------------------------------------------
# B. Ledger creation
# ---------------------------------------------------------------------------

class TestLedgerCreation:
    def test_returns_zero(self, tmp_path):
        h = _write_history(tmp_path, [_record(["build_portfolio_dashboard"])])
        out = tmp_path / "ledger.json"
        assert update_action_effectiveness_from_history(str(h), str(out)) == 0

    def test_output_file_created(self, tmp_path):
        h = _write_history(tmp_path, [_record(["build_portfolio_dashboard"])])
        out = tmp_path / "ledger.json"
        update_action_effectiveness_from_history(str(h), str(out))
        assert out.exists()

    def test_output_is_valid_json(self, tmp_path):
        h = _write_history(tmp_path, [_record(["artifact_audit_example"])])
        out = tmp_path / "ledger.json"
        update_action_effectiveness_from_history(str(h), str(out))
        data = json.loads(out.read_text())
        assert isinstance(data, dict)

    def test_output_has_trailing_newline(self, tmp_path):
        h = _write_history(tmp_path, [_record(["artifact_audit_example"])])
        out = tmp_path / "ledger.json"
        update_action_effectiveness_from_history(str(h), str(out))
        assert out.read_text(encoding="utf-8").endswith("\n")

    def test_output_has_actions_key(self, tmp_path):
        h = _write_history(tmp_path, [_record(["build_portfolio_dashboard"])])
        out = tmp_path / "ledger.json"
        update_action_effectiveness_from_history(str(h), str(out))
        data = json.loads(out.read_text())
        assert "actions" in data

    def test_task_entry_present(self, tmp_path):
        h = _write_history(tmp_path, [_record(["build_portfolio_dashboard"])])
        out = tmp_path / "ledger.json"
        update_action_effectiveness_from_history(str(h), str(out))
        data = json.loads(out.read_text())
        assert "build_portfolio_dashboard" in data["actions"]

    def test_empty_history_produces_empty_actions(self, tmp_path):
        h = _write_history(tmp_path, [])
        out = tmp_path / "ledger.json"
        update_action_effectiveness_from_history(str(h), str(out))
        data = json.loads(out.read_text())
        assert data["actions"] == {}

    def test_creates_parent_dirs(self, tmp_path):
        h = _write_history(tmp_path, [_record(["build_portfolio_dashboard"])])
        out = tmp_path / "sub" / "ledger.json"
        rc = update_action_effectiveness_from_history(str(h), str(out))
        assert rc == 0
        assert out.exists()


# ---------------------------------------------------------------------------
# C. Idempotency
# ---------------------------------------------------------------------------

class TestIdempotency:
    def test_second_run_returns_zero(self, tmp_path):
        h = _write_history(tmp_path, [_record(["build_portfolio_dashboard"])])
        out = tmp_path / "ledger.json"
        update_action_effectiveness_from_history(str(h), str(out))
        rc = update_action_effectiveness_from_history(str(h), str(out))
        assert rc == 0

    def test_output_identical_on_repeat(self, tmp_path):
        h = _write_history(tmp_path, [_record(["build_portfolio_dashboard"])])
        out = tmp_path / "ledger.json"
        update_action_effectiveness_from_history(str(h), str(out))
        text1 = out.read_text(encoding="utf-8")
        update_action_effectiveness_from_history(str(h), str(out))
        text2 = out.read_text(encoding="utf-8")
        assert text1 == text2

    def test_three_runs_stable(self, tmp_path):
        records = [
            _record(["build_portfolio_dashboard"], "ok"),
            _record(["artifact_audit_example"], "aborted"),
        ]
        h = _write_history(tmp_path, records)
        out = tmp_path / "ledger.json"
        texts = []
        for _ in range(3):
            update_action_effectiveness_from_history(str(h), str(out))
            texts.append(out.read_text(encoding="utf-8"))
        assert texts[0] == texts[1] == texts[2]


# ---------------------------------------------------------------------------
# D. Multi-record accumulation
# ---------------------------------------------------------------------------

class TestAccumulation:
    def test_two_ok_records_same_task(self, tmp_path):
        h = _write_history(tmp_path, [
            _record(["build_portfolio_dashboard"], "ok"),
            _record(["build_portfolio_dashboard"], "ok"),
        ])
        out = tmp_path / "ledger.json"
        update_action_effectiveness_from_history(str(h), str(out))
        data = json.loads(out.read_text())
        entry = data["actions"]["build_portfolio_dashboard"]
        assert entry["total_runs"] == 2
        assert entry["success_count"] == 2
        assert entry["failure_count"] == 0

    def test_mixed_ok_and_failure(self, tmp_path):
        h = _write_history(tmp_path, [
            _record(["artifact_audit_example"], "ok"),
            _record(["artifact_audit_example"], "aborted"),
            _record(["artifact_audit_example"], "ok"),
        ])
        out = tmp_path / "ledger.json"
        update_action_effectiveness_from_history(str(h), str(out))
        data = json.loads(out.read_text())
        entry = data["actions"]["artifact_audit_example"]
        assert entry["total_runs"] == 3
        assert entry["success_count"] == 2
        assert entry["failure_count"] == 1
        assert entry["last_status"] == "ok"

    def test_two_distinct_tasks(self, tmp_path):
        h = _write_history(tmp_path, [
            _record(["build_portfolio_dashboard"], "ok"),
            _record(["repo_insights_example"], "aborted"),
        ])
        out = tmp_path / "ledger.json"
        update_action_effectiveness_from_history(str(h), str(out))
        data = json.loads(out.read_text())
        assert data["actions"]["build_portfolio_dashboard"]["success_count"] == 1
        assert data["actions"]["repo_insights_example"]["failure_count"] == 1

    def test_actions_sorted_by_key(self, tmp_path):
        h = _write_history(tmp_path, [
            _record(["zzz_task"], "ok"),
            _record(["aaa_task"], "ok"),
        ])
        out = tmp_path / "ledger.json"
        update_action_effectiveness_from_history(str(h), str(out))
        data = json.loads(out.read_text())
        keys = list(data["actions"].keys())
        assert keys == sorted(keys)


# ---------------------------------------------------------------------------
# E. Non-ok status
# ---------------------------------------------------------------------------

class TestNonOkStatus:
    def test_aborted_status_increments_failure(self, tmp_path):
        h = _write_history(tmp_path, [_record(["build_portfolio_dashboard"], "aborted")])
        out = tmp_path / "ledger.json"
        update_action_effectiveness_from_history(str(h), str(out))
        data = json.loads(out.read_text())
        entry = data["actions"]["build_portfolio_dashboard"]
        assert entry["failure_count"] == 1
        assert entry["success_count"] == 0

    def test_none_status_treated_as_failure(self, tmp_path):
        h = _write_history(tmp_path, [{"selected_tasks": ["build_portfolio_dashboard"], "status": None}])
        out = tmp_path / "ledger.json"
        update_action_effectiveness_from_history(str(h), str(out))
        data = json.loads(out.read_text())
        entry = data["actions"]["build_portfolio_dashboard"]
        assert entry["failure_count"] == 1
        assert entry["success_count"] == 0

    def test_unknown_status_treated_as_failure(self, tmp_path):
        h = _write_history(tmp_path, [_record(["build_portfolio_dashboard"], "unknown_status")])
        out = tmp_path / "ledger.json"
        update_action_effectiveness_from_history(str(h), str(out))
        data = json.loads(out.read_text())
        entry = data["actions"]["build_portfolio_dashboard"]
        assert entry["failure_count"] == 1
        assert entry["success_count"] == 0


# ---------------------------------------------------------------------------
# F. Error cases
# ---------------------------------------------------------------------------

class TestErrorCases:
    def test_returns_one_when_history_missing(self, tmp_path):
        out = tmp_path / "ledger.json"
        rc = update_action_effectiveness_from_history(
            str(tmp_path / "nonexistent.json"), str(out)
        )
        assert rc == 1

    def test_returns_one_when_history_bad_json(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("not json", encoding="utf-8")
        out = tmp_path / "ledger.json"
        rc = update_action_effectiveness_from_history(str(bad), str(out))
        assert rc == 1

    def test_returns_one_when_records_missing(self, tmp_path):
        p = tmp_path / "h.json"
        p.write_text(json.dumps({"not_records": []}) + "\n", encoding="utf-8")
        out = tmp_path / "ledger.json"
        rc = update_action_effectiveness_from_history(str(p), str(out))
        assert rc == 1

    def test_returns_one_when_records_not_list(self, tmp_path):
        p = tmp_path / "h.json"
        p.write_text(json.dumps({"records": "bad"}) + "\n", encoding="utf-8")
        out = tmp_path / "ledger.json"
        rc = update_action_effectiveness_from_history(str(p), str(out))
        assert rc == 1
