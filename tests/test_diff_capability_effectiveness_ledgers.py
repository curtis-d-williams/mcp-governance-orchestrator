# SPDX-License-Identifier: MIT
"""Tests for scripts/diff_capability_effectiveness_ledgers.py."""

import importlib.util
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_SCRIPT = _REPO_ROOT / "scripts" / "diff_capability_effectiveness_ledgers.py"
_spec = importlib.util.spec_from_file_location("diff_capability_effectiveness_ledgers", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

_load_ledger       = _mod._load_ledger
_diff_capabilities = _mod._diff_capabilities
build_diff_report  = _mod.build_diff_report
main               = _mod.main


def _write_ledger(path: Path, capabilities: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"capabilities": capabilities}, indent=2) + "\n",
        encoding="utf-8",
    )


def _cap(total=1, successful=1, failed=0, evolved=0, status="ok", source="repair"):
    return {
        "artifact_kind": "mcp_server",
        "total_syntheses": total,
        "successful_syntheses": successful,
        "failed_syntheses": failed,
        "successful_evolved_syntheses": evolved,
        "last_synthesis_status": status,
        "last_synthesis_source": source,
        "last_synthesis_used_evolution": False,
    }


# ---------------------------------------------------------------------------
# _load_ledger
# ---------------------------------------------------------------------------

def test_load_ledger_missing_file_raises(tmp_path):
    import pytest
    with pytest.raises(ValueError, match="not found"):
        _load_ledger(tmp_path / "nope.json")


def test_load_ledger_missing_capabilities_key_raises(tmp_path):
    import pytest
    p = tmp_path / "bad.json"
    p.write_text('{"other": {}}', encoding="utf-8")
    with pytest.raises(ValueError, match="missing required key"):
        _load_ledger(p)


# ---------------------------------------------------------------------------
# _diff_capabilities
# ---------------------------------------------------------------------------

def test_added_capability_detected():
    before = {}
    after = {"new_cap": _cap()}
    result = _diff_capabilities(before, after)
    assert result["added"] == ["new_cap"]
    assert result["removed"] == []
    assert result["summary"]["added_count"] == 1


def test_removed_capability_detected():
    before = {"old_cap": _cap()}
    after = {}
    result = _diff_capabilities(before, after)
    assert result["removed"] == ["old_cap"]
    assert result["added"] == []
    assert result["summary"]["removed_count"] == 1


def test_changed_field_detected():
    before = {"cap_a": _cap(total=1, successful=1)}
    after  = {"cap_a": _cap(total=2, successful=2)}
    result = _diff_capabilities(before, after)
    assert "cap_a" in result["changed"]
    assert result["changed"]["cap_a"]["total_syntheses"] == {"before": 1, "after": 2}
    assert result["changed"]["cap_a"]["successful_syntheses"] == {"before": 1, "after": 2}


def test_unchanged_capability_not_in_changed():
    entry = _cap()
    result = _diff_capabilities({"cap_a": entry}, {"cap_a": entry})
    assert "cap_a" not in result["changed"]
    assert "cap_a" in result["unchanged"]
    assert result["summary"]["unchanged_count"] == 1


def test_identical_ledgers_produce_empty_diff():
    caps = {"cap_a": _cap(), "cap_b": _cap(total=3, successful=2, failed=1)}
    result = _diff_capabilities(caps, caps)
    assert result["added"] == []
    assert result["removed"] == []
    assert result["changed"] == {}
    assert result["summary"]["added_count"] == 0
    assert result["summary"]["changed_count"] == 0


def test_empty_before_all_capabilities_added():
    after = {"cap_a": _cap(), "cap_b": _cap()}
    result = _diff_capabilities({}, after)
    assert sorted(result["added"]) == ["cap_a", "cap_b"]
    assert result["summary"]["added_count"] == 2
    assert result["summary"]["removed_count"] == 0


def test_summary_counts_correct_mixed():
    before = {"keep": _cap(total=1), "remove": _cap(), "change": _cap(total=1)}
    after  = {"keep": _cap(total=1), "add": _cap(), "change": _cap(total=2)}
    result = _diff_capabilities(before, after)
    assert result["summary"]["added_count"] == 1
    assert result["summary"]["removed_count"] == 1
    assert result["summary"]["changed_count"] == 1
    assert result["summary"]["unchanged_count"] == 1


# ---------------------------------------------------------------------------
# main (integration)
# ---------------------------------------------------------------------------

def test_main_writes_output_file(tmp_path):
    before_path = tmp_path / "before.json"
    after_path  = tmp_path / "after.json"
    output_path = tmp_path / "diff.json"
    _write_ledger(before_path, {"cap_a": _cap(total=1)})
    _write_ledger(after_path,  {"cap_a": _cap(total=2), "cap_b": _cap()})
    rc = main(["--before", str(before_path), "--after", str(after_path),
               "--output", str(output_path)])
    assert rc == 0
    assert output_path.exists()
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["summary"]["added_count"] == 1
    assert report["summary"]["changed_count"] == 1


def test_main_missing_before_returns_nonzero(tmp_path):
    after_path = tmp_path / "after.json"
    _write_ledger(after_path, {})
    rc = main(["--before", str(tmp_path / "missing.json"), "--after", str(after_path)])
    assert rc != 0
