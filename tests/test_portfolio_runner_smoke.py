import json
import subprocess
import sys
from pathlib import Path


def _run(args):
    r = subprocess.run([sys.executable, "-m", "mcp_governance_orchestrator.portfolio", *args], capture_output=True, text=True)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def test_portfolio_run_is_deterministic_and_ok_on_self_repo(tmp_path: Path):
    repos_path = tmp_path / "repos.json"
    repos_path.write_text(json.dumps({"repos": [{"id": "self", "path": "."}]}, indent=2, sort_keys=True) + "\n")

    code1, out1, err1 = _run(["run", "--policy", "policies/default.json", "--repos", str(repos_path)])
    code2, out2, err2 = _run(["run", "--policy", "policies/default.json", "--repos", str(repos_path)])

    assert err1 == ""
    assert err2 == ""
    assert code1 == 0
    assert code2 == 0
    assert out1 == out2  # canonical + deterministic

    data = json.loads(out1)
    assert data["tool"] == "portfolio_run"
    assert data["ok"] is True
    assert data["fail_closed"] is False
    assert data["summary"]["repos_total"] == 1
    assert data["repos"][0]["returncode"] == 0


def test_portfolio_invalid_repos_file_fails_schema(tmp_path: Path):
    repos_path = tmp_path / "repos.json"
    repos_path.write_text(json.dumps({"nope": []}) + "\n")

    code, out, err = _run(["run", "--policy", "policies/default.json", "--repos", str(repos_path)])
    assert err == ""
    assert code == 3
    data = json.loads(out)
    assert data["ok"] is False
    assert data["fail_closed"] is True
    assert data["error"]["error_type"] in ("portfolio_schema", "portfolio_load")
