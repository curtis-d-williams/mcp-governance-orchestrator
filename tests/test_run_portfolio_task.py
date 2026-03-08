import json
import subprocess
from pathlib import Path


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
