# SPDX-License-Identifier: MIT
"""Tests for scripts/build_capability_effectiveness_dashboard.py."""

import importlib.util
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_SCRIPT = _REPO_ROOT / "scripts" / "build_capability_effectiveness_dashboard.py"
_spec = importlib.util.spec_from_file_location("build_capability_effectiveness_dashboard", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

_load_ledger = _mod._load_ledger
_sort_rows   = _mod._sort_rows
_build_rows  = _mod._build_rows
_build_html  = _mod._build_html
main         = _mod.main


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# _load_ledger
# ---------------------------------------------------------------------------

def test_load_ledger_missing_file_raises(tmp_path):
    import pytest
    with pytest.raises(ValueError, match="not found"):
        _load_ledger(tmp_path / "nonexistent.json")


def test_load_ledger_malformed_json_raises(tmp_path):
    import pytest
    p = tmp_path / "bad.json"
    p.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(ValueError, match="malformed JSON"):
        _load_ledger(p)


def test_load_ledger_missing_capabilities_key_raises(tmp_path):
    import pytest
    p = tmp_path / "ledger.json"
    _write_json(p, {"other": {}})
    with pytest.raises(ValueError, match="missing required key 'capabilities'"):
        _load_ledger(p)


def test_load_ledger_valid_returns_dict(tmp_path):
    p = tmp_path / "ledger.json"
    _write_json(p, {"capabilities": {}})
    result = _load_ledger(p)
    assert result == {"capabilities": {}}


# ---------------------------------------------------------------------------
# _sort_rows
# ---------------------------------------------------------------------------

def test_sort_rows_total_syntheses_desc_then_capability_asc():
    rows = [
        {"capability": "b_cap", "total_syntheses": 5},
        {"capability": "a_cap", "total_syntheses": 5},
        {"capability": "c_cap", "total_syntheses": 10},
    ]
    result = _sort_rows(rows)
    assert [r["capability"] for r in result] == ["c_cap", "a_cap", "b_cap"]


# ---------------------------------------------------------------------------
# _build_rows
# ---------------------------------------------------------------------------

def test_build_rows_derives_success_rate():
    caps = {
        "my_cap": {
            "artifact_kind": "mcp_server",
            "total_syntheses": 4,
            "successful_syntheses": 3,
            "failed_syntheses": 1,
            "successful_evolved_syntheses": 1,
            "last_synthesis_status": "ok",
            "last_synthesis_source": "planner_request",
            "last_synthesis_used_evolution": True,
        }
    }
    rows = _build_rows(caps)
    assert len(rows) == 1
    assert rows[0]["success_rate"] == 0.75
    assert rows[0]["capability"] == "my_cap"


def test_build_rows_zero_total_syntheses_no_division_error():
    caps = {"empty_cap": {"total_syntheses": 0, "successful_syntheses": 0, "failed_syntheses": 0,
                          "successful_evolved_syntheses": 0}}
    rows = _build_rows(caps)
    assert rows[0]["success_rate"] == 0.0


def test_build_rows_similarity_fields_present():
    caps = {
        "sim_cap": {
            "total_syntheses": 2,
            "successful_syntheses": 2,
            "failed_syntheses": 0,
            "successful_evolved_syntheses": 1,
            "similarity_score": 0.85,
            "similarity_delta": 0.12,
        }
    }
    rows = _build_rows(caps)
    assert rows[0]["similarity_score"] == 0.85
    assert rows[0]["similarity_delta"] == 0.12


def test_build_rows_similarity_fields_absent_empty_string():
    caps = {"no_sim": {"total_syntheses": 1, "successful_syntheses": 1,
                       "failed_syntheses": 0, "successful_evolved_syntheses": 0}}
    rows = _build_rows(caps)
    assert rows[0]["similarity_score"] == ""
    assert rows[0]["similarity_delta"] == ""


# ---------------------------------------------------------------------------
# _build_html
# ---------------------------------------------------------------------------

def test_build_html_empty_capabilities_renders_table():
    html_out = _build_html({"capabilities": {}})
    assert "Capability Effectiveness Dashboard" in html_out
    assert "<table>" in html_out
    assert "Capabilities Tracked" in html_out


def test_build_html_single_row_contains_capability_name():
    ledger = {
        "capabilities": {
            "github_mcp": {
                "artifact_kind": "mcp_server",
                "total_syntheses": 3,
                "successful_syntheses": 3,
                "failed_syntheses": 0,
                "successful_evolved_syntheses": 1,
                "last_synthesis_status": "ok",
                "last_synthesis_source": "planner_request",
                "last_synthesis_used_evolution": True,
            }
        }
    }
    html_out = _build_html(ledger)
    assert "github_mcp" in html_out
    assert "mcp_server" in html_out
    assert "planner_request" in html_out


# ---------------------------------------------------------------------------
# main (integration)
# ---------------------------------------------------------------------------

def test_main_writes_output_file(tmp_path):
    input_path = tmp_path / "cap_ledger.json"
    output_path = tmp_path / "dashboard.html"
    _write_json(input_path, {
        "capabilities": {
            "test_cap": {
                "artifact_kind": "mcp_server",
                "total_syntheses": 1,
                "successful_syntheses": 1,
                "failed_syntheses": 0,
                "successful_evolved_syntheses": 0,
                "last_synthesis_status": "ok",
                "last_synthesis_source": "repair",
                "last_synthesis_used_evolution": False,
            }
        }
    })
    rc = main(["--input", str(input_path), "--output", str(output_path)])
    assert rc == 0
    assert output_path.exists()
    content = output_path.read_text(encoding="utf-8")
    assert "test_cap" in content


def test_main_missing_input_returns_nonzero(tmp_path):
    rc = main(["--input", str(tmp_path / "missing.json"), "--output", str(tmp_path / "out.html")])
    assert rc != 0
