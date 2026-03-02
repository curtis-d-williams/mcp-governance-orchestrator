from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _run_portfolio(args: list[str]) -> dict:
    r = subprocess.run(
        [sys.executable, "-m", "mcp_governance_orchestrator.portfolio", *args],
        capture_output=True,
        text=True,
    )
    # portfolio always prints canonical JSON on stdout
    assert r.stdout.strip(), f"expected stdout, got stderr={r.stderr!r}"
    return json.loads(r.stdout)


def _write_repos_json(tmp_path: Path, repo_dir: Path) -> Path:
    repos_path = tmp_path / "repos.json"
    repos_path.write_text(
        json.dumps({"repos": [{"id": "r1", "path": str(repo_dir)}]}),
        encoding="utf-8",
    )
    return repos_path


def test_repo_registry_source_is_repo_when_present(tmp_path: Path):
    repo_dir = tmp_path / "repo_with_registry"
    (repo_dir / "config").mkdir(parents=True)
    # Presence-only: contents not required for provenance (and run-policy uses orchestrator fallback registry anyway).
    (repo_dir / "config" / "guardians.json").write_text("{}", encoding="utf-8")

    repos_path = _write_repos_json(tmp_path, repo_dir)

    data = _run_portfolio(
        ["run", "--policy", "policies/default.json", "--repos", str(repos_path), "--include-registry-source"]
    )
    repo0 = data["repos"][0]
    stdout_json = repo0["stdout_json"]
    assert isinstance(stdout_json, dict)
    assert stdout_json["registry"]["source"] == "repo"
    assert stdout_json["registry"]["path"].endswith(str(Path("config") / "guardians.json"))
    assert Path(stdout_json["registry"]["path"]).resolve().as_posix().endswith(
        (repo_dir / "config" / "guardians.json").resolve().as_posix()
    )


def test_repo_registry_source_is_fallback_when_missing(tmp_path: Path):
    repo_dir = tmp_path / "repo_without_registry"
    repo_dir.mkdir(parents=True)

    repos_path = _write_repos_json(tmp_path, repo_dir)

    data = _run_portfolio(
        ["run", "--policy", "policies/default.json", "--repos", str(repos_path), "--include-registry-source"]
    )
    repo0 = data["repos"][0]
    stdout_json = repo0["stdout_json"]
    assert isinstance(stdout_json, dict)
    assert stdout_json["registry"]["source"] == "fallback"
    # should be the orchestrator's fallback config/guardians.json
    assert stdout_json["registry"]["path"].endswith(str(Path("config") / "guardians.json"))


def test_portfolio_output_deterministic_with_registry_source_flag(tmp_path: Path):
    repo_dir = tmp_path / "repo_without_registry"
    repo_dir.mkdir(parents=True)
    repos_path = _write_repos_json(tmp_path, repo_dir)

    args = ["run", "--policy", "policies/default.json", "--repos", str(repos_path), "--include-registry-source"]
    d1 = _run_portfolio(args)
    d2 = _run_portfolio(args)
    assert d1 == d2
