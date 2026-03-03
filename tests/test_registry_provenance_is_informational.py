import json
import subprocess
import sys
from pathlib import Path


def _write_repos_json(tmp_path: Path, repo_root: Path) -> Path:
    """
    Hermetic repos file: only references the current repo.
    This is sufficient to validate that registry provenance is informational-only.
    """
    repos_path = tmp_path / "repos.json"
    payload = {"repos": [{"id": "mcp-governance-orchestrator", "path": str(repo_root)}]}
    repos_path.write_text(json.dumps(payload), encoding="utf-8")
    return repos_path


def _run_portfolio(repo_root: Path, repos_path: Path, include_registry_source: bool) -> dict:
    cmd = [
        sys.executable,
        "-m",
        "mcp_governance_orchestrator.portfolio",
        "run",
        "--policy",
        "policies/default.json",
        "--repos",
        str(repos_path),
    ]
    if include_registry_source:
        cmd.append("--include-registry-source")

    p = subprocess.run(cmd, cwd=str(repo_root), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    assert p.returncode == 0, f"portfolio runner failed: rc={p.returncode}\nstderr:\n{p.stderr}\nstdout:\n{p.stdout}"
    return json.loads(p.stdout)


def _strip_registry_field(envelope: dict) -> dict:
    """
    Remove stdout_json.registry from each repo result so we can compare
    'with flag' vs 'without flag' and ensure provenance is informational only.
    """
    repos = envelope.get("repos", [])
    if not isinstance(repos, list):
        return envelope

    for r in repos:
        if not isinstance(r, dict):
            continue
        stdout_json = r.get("stdout_json")
        if isinstance(stdout_json, dict):
            stdout_json.pop("registry", None)
    return envelope


def test_registry_provenance_is_informational_only(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    repos_path = _write_repos_json(tmp_path, repo_root)

    base = _run_portfolio(repo_root, repos_path, include_registry_source=False)
    prov = _run_portfolio(repo_root, repos_path, include_registry_source=True)

    # Sanity: when enabled, at least one repo should carry provenance
    assert any(
        isinstance(r, dict)
        and isinstance(r.get("stdout_json"), dict)
        and isinstance(r["stdout_json"].get("registry"), dict)
        for r in prov.get("repos", [])
    ), "expected at least one repo to include stdout_json.registry when flag enabled"

    # Key invariant: aside from the injected metadata, output must match exactly
    assert _strip_registry_field(prov) == base
