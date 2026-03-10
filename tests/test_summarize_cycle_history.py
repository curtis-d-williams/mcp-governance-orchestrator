# SPDX-License-Identifier: MIT
"""Tests for scripts/summarize_cycle_history.py."""

import csv
import importlib.util
import json
import sys
from io import StringIO
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Module loading
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_SCRIPT = _REPO_ROOT / "scripts" / "summarize_cycle_history.py"
_spec = importlib.util.spec_from_file_location("summarize_cycle_history", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

summarize_cycle_history = _mod.summarize_cycle_history
_extract_timestamp = _mod._extract_timestamp
_extract_selected_actions = _mod._extract_selected_actions
_extract_risk_level = _mod._extract_risk_level
_summarize_cycle_file = _mod._summarize_cycle_file


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_TS_A = "2026-01-01T10-00-00"
_TS_B = "2026-01-01T10-00-01"
_TS_C = "2026-01-01T10-00-02"


def _cycle(status="ok", phase=None, governed_result=None):
    """Return a minimal cycle artifact dict."""
    return {
        "status": status,
        **({"phase": phase} if phase is not None else {}),
        "governed_result": governed_result or {},
    }


def _governed_result(
    selected_actions=None,
    attempts=None,
    abort_reason=None,
    result=None,
):
    """Return a governed_result sub-dict."""
    gr = {}
    if selected_actions is not None:
        gr["selected_actions"] = selected_actions
    if attempts is not None:
        gr["attempts"] = attempts
    if abort_reason is not None:
        gr["abort_reason"] = abort_reason
    if result is not None:
        gr["result"] = result
    return gr


def _write(tmp_path, filename, data):
    """Write a cycle artifact JSON file into tmp_path."""
    p = tmp_path / filename
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# 1. Empty archive dir returns []
# ---------------------------------------------------------------------------

def test_empty_archive_dir_returns_empty_list(tmp_path):
    archive_dir = tmp_path / "cycles"
    archive_dir.mkdir()
    assert summarize_cycle_history(str(archive_dir)) == []


# ---------------------------------------------------------------------------
# 2. Missing archive dir returns []
# ---------------------------------------------------------------------------

def test_missing_archive_dir_returns_empty_list(tmp_path):
    assert summarize_cycle_history(str(tmp_path / "nonexistent")) == []


# ---------------------------------------------------------------------------
# 3. Single valid cycle file summarized correctly
# ---------------------------------------------------------------------------

def test_single_valid_cycle_file(tmp_path):
    archive_dir = tmp_path / "cycles"
    archive_dir.mkdir()
    gr = _governed_result(
        selected_actions=["build_portfolio_dashboard"],
        attempts=[{"offset": 0, "risk_level": "low_risk"}],
    )
    _write(archive_dir, f"{_TS_A}_cycle.json", _cycle(status="ok", governed_result=gr))

    rows = summarize_cycle_history(str(archive_dir))
    assert len(rows) == 1
    r = rows[0]
    assert r["filename"] == f"{_TS_A}_cycle.json"
    assert r["timestamp"] == _TS_A
    assert r["status"] == "ok"
    assert r["phase"] is None
    assert r["selected_actions"] == ["build_portfolio_dashboard"]
    assert r["selected_actions_count"] == 1
    assert r["risk_level"] == "low_risk"
    assert r["attempts_count"] == 1
    assert r["abort_reason"] is None


# ---------------------------------------------------------------------------
# 4. Multiple files sorted chronologically by filename
# ---------------------------------------------------------------------------

def test_multiple_files_sorted_chronologically(tmp_path):
    archive_dir = tmp_path / "cycles"
    archive_dir.mkdir()
    _write(archive_dir, f"{_TS_B}_cycle.json", _cycle(status="ok"))
    _write(archive_dir, f"{_TS_A}_cycle.json", _cycle(status="aborted"))
    _write(archive_dir, f"{_TS_C}_cycle.json", _cycle(status="ok"))

    rows = summarize_cycle_history(str(archive_dir))
    assert len(rows) == 3
    assert [r["timestamp"] for r in rows] == [_TS_A, _TS_B, _TS_C]


# ---------------------------------------------------------------------------
# 5. Suffixed filenames derive the same timestamp prefix
# ---------------------------------------------------------------------------

def test_extract_timestamp_base_filename():
    assert _extract_timestamp(f"{_TS_A}_cycle.json") == _TS_A


def test_extract_timestamp_suffixed_filename():
    assert _extract_timestamp(f"{_TS_A}_cycle_1.json") == _TS_A


def test_extract_timestamp_suffix_2():
    assert _extract_timestamp(f"{_TS_A}_cycle_2.json") == _TS_A


def test_suffixed_file_in_summary(tmp_path):
    archive_dir = tmp_path / "cycles"
    archive_dir.mkdir()
    _write(archive_dir, f"{_TS_A}_cycle_1.json", _cycle(status="ok"))

    rows = summarize_cycle_history(str(archive_dir))
    assert rows[0]["timestamp"] == _TS_A
    assert rows[0]["filename"] == f"{_TS_A}_cycle_1.json"


# ---------------------------------------------------------------------------
# 6. selected_actions from governed_result["selected_actions"]
# ---------------------------------------------------------------------------

def test_selected_actions_from_governed_result_direct(tmp_path):
    archive_dir = tmp_path / "cycles"
    archive_dir.mkdir()
    gr = _governed_result(selected_actions=["task_a", "task_b"])
    _write(archive_dir, f"{_TS_A}_cycle.json", _cycle(governed_result=gr))

    rows = summarize_cycle_history(str(archive_dir))
    assert rows[0]["selected_actions"] == ["task_a", "task_b"]
    assert rows[0]["selected_actions_count"] == 2


# ---------------------------------------------------------------------------
# 7. Fallback selected_actions from governed_result["result"]["selected_actions"]
# ---------------------------------------------------------------------------

def test_selected_actions_fallback_from_result(tmp_path):
    archive_dir = tmp_path / "cycles"
    archive_dir.mkdir()
    gr = _governed_result(result={"selected_actions": ["fallback_task"]})
    _write(archive_dir, f"{_TS_A}_cycle.json", _cycle(governed_result=gr))

    rows = summarize_cycle_history(str(archive_dir))
    assert rows[0]["selected_actions"] == ["fallback_task"]


def test_selected_actions_direct_takes_priority_over_fallback():
    gr = _governed_result(
        selected_actions=["direct"],
        result={"selected_actions": ["fallback"]},
    )
    assert _extract_selected_actions(gr) == ["direct"]


def test_selected_actions_empty_when_absent():
    assert _extract_selected_actions({}) == []


# ---------------------------------------------------------------------------
# 8. risk_level extracted from last attempt
# ---------------------------------------------------------------------------

def test_risk_level_from_last_attempt(tmp_path):
    archive_dir = tmp_path / "cycles"
    archive_dir.mkdir()
    gr = _governed_result(attempts=[
        {"offset": 0, "risk_level": "high_risk"},
        {"offset": 1, "risk_level": "moderate_risk"},
    ])
    _write(archive_dir, f"{_TS_A}_cycle.json", _cycle(governed_result=gr))

    rows = summarize_cycle_history(str(archive_dir))
    assert rows[0]["risk_level"] == "moderate_risk"


def test_risk_level_none_when_no_attempts():
    assert _extract_risk_level({}) is None
    assert _extract_risk_level({"attempts": []}) is None


# ---------------------------------------------------------------------------
# 9. attempts_count computed correctly
# ---------------------------------------------------------------------------

def test_attempts_count(tmp_path):
    archive_dir = tmp_path / "cycles"
    archive_dir.mkdir()
    gr = _governed_result(attempts=[
        {"offset": 0, "risk_level": "high_risk"},
        {"offset": 1, "risk_level": "low_risk"},
        {"offset": 2, "risk_level": "low_risk"},
    ])
    _write(archive_dir, f"{_TS_A}_cycle.json", _cycle(governed_result=gr))

    rows = summarize_cycle_history(str(archive_dir))
    assert rows[0]["attempts_count"] == 3


def test_attempts_count_zero_when_absent(tmp_path):
    archive_dir = tmp_path / "cycles"
    archive_dir.mkdir()
    _write(archive_dir, f"{_TS_A}_cycle.json", _cycle(governed_result={}))

    rows = summarize_cycle_history(str(archive_dir))
    assert rows[0]["attempts_count"] == 0


# ---------------------------------------------------------------------------
# 10. abort_reason extracted correctly
# ---------------------------------------------------------------------------

def test_abort_reason_extracted(tmp_path):
    archive_dir = tmp_path / "cycles"
    archive_dir.mkdir()
    gr = _governed_result(abort_reason="high_risk_persistent")
    _write(archive_dir, f"{_TS_A}_cycle.json",
           _cycle(status="aborted", phase="governed_loop", governed_result=gr))

    rows = summarize_cycle_history(str(archive_dir))
    assert rows[0]["abort_reason"] == "high_risk_persistent"
    assert rows[0]["phase"] == "governed_loop"
    assert rows[0]["status"] == "aborted"


def test_abort_reason_none_on_ok_cycle(tmp_path):
    archive_dir = tmp_path / "cycles"
    archive_dir.mkdir()
    _write(archive_dir, f"{_TS_A}_cycle.json", _cycle(status="ok"))

    rows = summarize_cycle_history(str(archive_dir))
    assert rows[0]["abort_reason"] is None


# ---------------------------------------------------------------------------
# 11. Invalid JSON file is skipped
# ---------------------------------------------------------------------------

def test_invalid_json_skipped(tmp_path):
    archive_dir = tmp_path / "cycles"
    archive_dir.mkdir()
    (archive_dir / f"{_TS_A}_cycle.json").write_text("not json{{", encoding="utf-8")
    _write(archive_dir, f"{_TS_B}_cycle.json", _cycle(status="ok"))

    rows = summarize_cycle_history(str(archive_dir))
    assert len(rows) == 1
    assert rows[0]["filename"] == f"{_TS_B}_cycle.json"


# ---------------------------------------------------------------------------
# 12. Partial / malformed cycle object yields best-effort row
# ---------------------------------------------------------------------------

def test_partial_cycle_no_governed_result(tmp_path):
    archive_dir = tmp_path / "cycles"
    archive_dir.mkdir()
    _write(archive_dir, f"{_TS_A}_cycle.json", {"status": "ok"})

    rows = summarize_cycle_history(str(archive_dir))
    assert len(rows) == 1
    r = rows[0]
    assert r["status"] == "ok"
    assert r["selected_actions"] == []
    assert r["attempts_count"] == 0
    assert r["abort_reason"] is None


def test_cycle_file_with_non_dict_root(tmp_path):
    """A file containing a JSON list (wrong shape) still produces a best-effort row."""
    archive_dir = tmp_path / "cycles"
    archive_dir.mkdir()
    p = archive_dir / f"{_TS_A}_cycle.json"
    p.write_text(json.dumps([1, 2, 3]), encoding="utf-8")

    rows = summarize_cycle_history(str(archive_dir))
    assert len(rows) == 1
    assert rows[0]["status"] is None


# ---------------------------------------------------------------------------
# 13. JSON stdout from main() is parseable
# ---------------------------------------------------------------------------

def test_json_stdout_parseable(tmp_path, capsys):
    archive_dir = tmp_path / "cycles"
    archive_dir.mkdir()
    _write(archive_dir, f"{_TS_A}_cycle.json", _cycle(status="ok"))

    _mod.main(["--archive-dir", str(archive_dir)])
    out = capsys.readouterr().out
    data = json.loads(out)
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["status"] == "ok"


def test_json_stdout_empty_archive(tmp_path, capsys):
    archive_dir = tmp_path / "cycles"
    archive_dir.mkdir()

    _mod.main(["--archive-dir", str(archive_dir)])
    out = capsys.readouterr().out
    assert json.loads(out) == []


# ---------------------------------------------------------------------------
# 14. CSV stdout has header and expected row values
# ---------------------------------------------------------------------------

def test_csv_stdout_has_header(tmp_path, capsys):
    archive_dir = tmp_path / "cycles"
    archive_dir.mkdir()

    _mod.main(["--archive-dir", str(archive_dir), "--format", "csv"])
    out = capsys.readouterr().out
    rows = list(csv.reader(StringIO(out)))
    assert rows[0] == _mod._CSV_FIELDS


def test_csv_stdout_row_values(tmp_path, capsys):
    archive_dir = tmp_path / "cycles"
    archive_dir.mkdir()
    gr = _governed_result(
        selected_actions=["build_portfolio_dashboard", "repo_insights_example"],
        attempts=[{"offset": 0, "risk_level": "low_risk"}],
    )
    _write(archive_dir, f"{_TS_A}_cycle.json", _cycle(status="ok", governed_result=gr))

    _mod.main(["--archive-dir", str(archive_dir), "--format", "csv"])
    out = capsys.readouterr().out
    rows = list(csv.reader(StringIO(out)))
    assert len(rows) == 2          # header + 1 data row
    data_row = rows[1]
    assert data_row[0] == f"{_TS_A}_cycle.json"   # filename
    assert data_row[1] == _TS_A                    # timestamp
    assert data_row[2] == "ok"                     # status
    # selected_actions semicolon-joined
    assert data_row[4] == "build_portfolio_dashboard;repo_insights_example"
    assert data_row[5] == "2"                      # selected_actions_count
    assert data_row[6] == "low_risk"               # risk_level


def test_csv_stdout_empty_archive_has_header_only(tmp_path, capsys):
    archive_dir = tmp_path / "cycles"
    archive_dir.mkdir()

    _mod.main(["--archive-dir", str(archive_dir), "--format", "csv"])
    out = capsys.readouterr().out
    rows = list(csv.reader(StringIO(out)))
    assert len(rows) == 1
    assert rows[0] == _mod._CSV_FIELDS


# ---------------------------------------------------------------------------
# 15. --output for json creates deterministic file
# ---------------------------------------------------------------------------

def test_output_json_file_created(tmp_path):
    archive_dir = tmp_path / "cycles"
    archive_dir.mkdir()
    gr = _governed_result(selected_actions=["task_a"])
    _write(archive_dir, f"{_TS_A}_cycle.json", _cycle(status="ok", governed_result=gr))

    out_file = tmp_path / "summary.json"
    _mod.main(["--archive-dir", str(archive_dir), "--output", str(out_file)])

    assert out_file.exists()
    data = json.loads(out_file.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["selected_actions"] == ["task_a"]


def test_output_json_file_ends_with_newline(tmp_path):
    archive_dir = tmp_path / "cycles"
    archive_dir.mkdir()
    _write(archive_dir, f"{_TS_A}_cycle.json", _cycle(status="ok"))

    out_file = tmp_path / "summary.json"
    _mod.main(["--archive-dir", str(archive_dir), "--output", str(out_file)])

    assert out_file.read_text(encoding="utf-8").endswith("\n")


# ---------------------------------------------------------------------------
# 16. --output for csv creates expected file
# ---------------------------------------------------------------------------

def test_output_csv_file_created(tmp_path):
    archive_dir = tmp_path / "cycles"
    archive_dir.mkdir()
    gr = _governed_result(
        selected_actions=["build_portfolio_dashboard"],
        attempts=[{"offset": 0, "risk_level": "moderate_risk"}],
        abort_reason=None,
    )
    _write(archive_dir, f"{_TS_A}_cycle.json", _cycle(status="ok", governed_result=gr))

    out_file = tmp_path / "summary.csv"
    _mod.main(["--archive-dir", str(archive_dir), "--output", str(out_file),
               "--format", "csv"])

    assert out_file.exists()
    rows = list(csv.reader(out_file.read_text(encoding="utf-8").splitlines()))
    assert rows[0] == _mod._CSV_FIELDS
    assert rows[1][2] == "ok"
    assert rows[1][4] == "build_portfolio_dashboard"
    assert rows[1][6] == "moderate_risk"
