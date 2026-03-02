import json
import subprocess
import sys
from pathlib import Path


def _run(args):
    r = subprocess.run(
        [sys.executable, "-m", "mcp_governance_orchestrator.portfolio", *args],
        capture_output=True,
        text=True,
    )
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def test_portfolio_output_contract_shape(tmp_path: Path):
    repos_path = tmp_path / "repos.json"
    repos_path.write_text(
        json.dumps({"repos": [{"id": "self", "path": "."}]}, indent=2, sort_keys=True) + "\n"
    )

    code, out, err = _run(
        ["run", "--policy", "policies/default.json", "--repos", str(repos_path)]
    )

    assert err == ""
    assert code == 0

    data = json.loads(out)

    # ---- Top-level keys locked ----
    expected_top = {
        "tool",
        "ok",
        "fail_closed",
        "policy_path",
        "repos_path",
        "repos",
        "summary",
    }
    assert set(data.keys()) == expected_top

    assert data["tool"] == "portfolio_run"
    assert data["ok"] is True
    assert data["fail_closed"] is False

    # ---- Summary keys locked ----
    expected_summary = {
        "repos_total",
        "repos_ok",
        "repos_failed",
        "repos_schema_or_load_errors",
    }
    assert set(data["summary"].keys()) == expected_summary

    # ---- Repo result shape locked ----
    assert isinstance(data["repos"], list)
    assert len(data["repos"]) == 1

    repo = data["repos"][0]
    expected_repo_keys = {
        "id",
        "path",
        "returncode",
        "ok",
        "fail_closed",
        "stdout_json",
        "stdout_raw",
        "stderr",
    }
    assert set(repo.keys()) == expected_repo_keys

    assert repo["id"] == "self"
    assert repo["returncode"] == 0
    assert repo["ok"] is True
    assert repo["fail_closed"] is False

    # stdout_json must exist for successful repo
    assert isinstance(repo["stdout_json"], dict)
    assert repo["stdout_raw"] == ""
    assert repo["stderr"] == ""
