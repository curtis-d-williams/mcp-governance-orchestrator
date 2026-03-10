import csv
import json
import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = str(_REPO_ROOT / "scripts" / "run_portfolio_task.py")


def test_run_portfolio_task_single_repo_manifest(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]

    manifest = tmp_path / "portfolio.json"
    manifest.write_text(json.dumps({
        "repos": [
            {"id": "mcp-governance-orchestrator", "path": str(repo_root)}
        ]
    }))

    result = subprocess.run(
        [
            "python3",
            "-m",
            "scripts.run_portfolio_task",
            "build_portfolio_dashboard",
            str(manifest),
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=repo_root,
    )

    payload = json.loads(result.stdout)

    assert payload["task_name"] == "build_portfolio_dashboard"
    assert payload["summary"] == {
        "repos_total": 1,
        "repos_ok": 1,
        "repos_failed": 0,
    }
    assert [repo["id"] for repo in payload["repos"]] == [
        "mcp-governance-orchestrator"
    ]
    assert payload["repos"][0]["ok"] is True
    assert payload["repos"][0]["result"]["task_name"] == "build_portfolio_dashboard"


# ---------------------------------------------------------------------------
# Single-task mode artifact-writing tests
# ---------------------------------------------------------------------------
# Run the script via its direct path (cwd=tmp_path) so artifacts land in
# tmp_path, matching how run_governed_portfolio_cycle.py invokes it.

def _run_single_task_in(tmp_path):
    """Invoke run_portfolio_task.py with one task, cwd=tmp_path; return CompletedProcess."""
    manifest = tmp_path / "portfolio.json"
    manifest.write_text(json.dumps({
        "repos": [{"id": "mcp-governance-orchestrator", "path": str(_REPO_ROOT)}]
    }), encoding="utf-8")
    return subprocess.run(
        ["python3", _SCRIPT, "build_portfolio_dashboard", str(manifest)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=True,
    )


def test_single_task_writes_tier3_portfolio_report_csv(tmp_path):
    """Single-task mode must write tier3_portfolio_report.csv into cwd."""
    _run_single_task_in(tmp_path)
    report = tmp_path / "tier3_portfolio_report.csv"
    assert report.exists(), "tier3_portfolio_report.csv not written in single-task mode"
    rows = list(csv.DictReader(report.read_text(encoding="utf-8").splitlines()))
    assert len(rows) == 1
    assert rows[0]["task"] == "build_portfolio_dashboard"
    assert rows[0]["repo_id"] == "mcp-governance-orchestrator"
    assert rows[0]["ok"] == "true"


def test_single_task_writes_tier3_multi_run_aggregate_json(tmp_path):
    """Single-task mode must write tier3_multi_run_aggregate.json into cwd."""
    _run_single_task_in(tmp_path)
    agg_path = tmp_path / "tier3_multi_run_aggregate.json"
    assert agg_path.exists(), "tier3_multi_run_aggregate.json not written in single-task mode"
    agg = json.loads(agg_path.read_text(encoding="utf-8"))
    assert isinstance(agg, list)
    assert len(agg) == 1
    assert agg[0]["task"] == "build_portfolio_dashboard"
    assert agg[0]["repo"] == "mcp-governance-orchestrator"
    assert agg[0]["ok"] is True


def test_single_task_stdout_json_backward_compatible(tmp_path):
    """Single-task mode stdout must still be valid JSON with the same top-level shape."""
    proc = _run_single_task_in(tmp_path)
    payload = json.loads(proc.stdout)
    assert payload["task_name"] == "build_portfolio_dashboard"
    assert "repos" in payload
    assert "summary" in payload
    assert payload["summary"]["repos_total"] == 1
