# SPDX-License-Identifier: MIT
"""Tests for scripts/run_portfolio_governance_batch.py."""

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_SCRIPT = _REPO_ROOT / "scripts" / "run_portfolio_governance_batch.py"
_spec = importlib.util.spec_from_file_location("run_portfolio_governance_batch", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

aggregate = _mod.aggregate
run_repo_cycle = _mod.run_repo_cycle


def _write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_aggregate_empty_results():
    summary, alert = aggregate([])

    assert summary == {
        "alerts_triggered": False,
        "repos_total": 0,
    }
    assert alert == {
        "alert": False,
    }


def test_aggregate_sets_alert_when_any_repo_alerts():
    summary, alert = aggregate([
        ({"status": "ok"}, {"alert": False}),
        ({"status": "ok"}, {"alert": True}),
    ])

    assert summary == {
        "alerts_triggered": True,
        "repos_total": 2,
    }
    assert alert == {
        "alert": True,
    }


def test_run_repo_cycle_writes_expected_paths_and_reads_outputs(tmp_path: Path):
    manifest_path = tmp_path / "manifest.json"
    output_dir = tmp_path / "portfolio_batch"
    repo_id = "repo_a"

    _write_json(manifest_path, {"repos": [{"id": repo_id}]})

    repo_dir = output_dir / repo_id
    cycle_output = repo_dir / "governed_cycle.json"
    summary_output = repo_dir / "summary.json"
    alert_output = repo_dir / "alert.json"

    expected_summary = {
        "alert_level": "none",
        "governance_decision": "continue",
        "status": "ok",
    }
    expected_alert = {
        "alert": False,
        "alert_level": "none",
        "reasons": [],
    }

    def fake_run(cmd, check):
        assert check is True
        assert cmd == [
            "python3",
            "scripts/run_scheduled_governed_cycle.py",
            "--manifest",
            str(manifest_path),
            "--output",
            str(cycle_output),
            "--summary-output",
            str(summary_output),
            "--alert-output",
            str(alert_output),
            "--repo-id",
            repo_id,
            "--task",
            "build_portfolio_dashboard",
        ]
        _write_json(summary_output, expected_summary)
        _write_json(alert_output, expected_alert)

    with patch("subprocess.run", side_effect=fake_run):
        summary, alert = run_repo_cycle(
            manifest_path,
            repo_id,
            ["build_portfolio_dashboard"],
            output_dir,
        )

    assert summary == expected_summary
    assert alert == expected_alert
