import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path


def _run(args):
    r = subprocess.run(
        [sys.executable, "-m", "mcp_governance_orchestrator.portfolio", *args],
        capture_output=True,
        text=True,
    )
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def _canonicalize_portfolio_contract(data: dict) -> dict:
    """
    Canonicalize ordering ONLY, without changing the frozen contract.
    Additionally, exclude repos_path from equality comparisons because
    it is an echo of the input path and will differ across temp files.

    - Sort repos list by repo id (contract field: "id")
    - For each repo, sort its stdout_json["guardians"] list by guardian_id if present
    """
    d = deepcopy(data)

    # Exclude path echo field from semantic comparisons (asserted separately)
    d.pop("repos_path", None)

    # Sort repos in portfolio envelope
    if isinstance(d.get("repos"), list):
        d["repos"] = sorted(d["repos"], key=lambda r: r.get("id", ""))

    # Sort guardians within each repo stdout_json (if shape supports it)
    for repo in d.get("repos", []):
        sj = repo.get("stdout_json")
        if isinstance(sj, dict) and isinstance(sj.get("guardians"), list):
            sj["guardians"] = sorted(sj["guardians"], key=lambda g: g.get("guardian_id", ""))

    return d


def _portfolio_run(policy_path: str, repos_path: Path) -> dict:
    code, out, err = _run(["run", "--policy", policy_path, "--repos", str(repos_path)])
    assert err == ""
    assert code == 0
    return json.loads(out)


def test_portfolio_aggregation_order_independent_over_repos_json(tmp_path: Path):
    """
    Portfolio aggregation invariant:
    Reordering repos.json input must not change portfolio semantics.
    We compare canonicalized (order-normalized) outputs.
    """
    policy = "policies/default.json"

    repos_a = tmp_path / "repos_a.json"
    repos_b = tmp_path / "repos_b.json"

    # Note: using "." for both is fine; invariant is about aggregation determinism
    repos_a.write_text(
        json.dumps(
            {"repos": [{"id": "a", "path": "."}, {"id": "b", "path": "."}]},
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    repos_b.write_text(
        json.dumps(
            {"repos": [{"id": "b", "path": "."}, {"id": "a", "path": "."}]},
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )

    out_a = _portfolio_run(policy, repos_a)
    out_b = _portfolio_run(policy, repos_b)

    # repos_path is an echo of the input path and should reflect each invocation
    assert out_a["repos_path"] == str(repos_a)
    assert out_b["repos_path"] == str(repos_b)

    assert _canonicalize_portfolio_contract(out_a) == _canonicalize_portfolio_contract(out_b)


def test_portfolio_ok_is_pure_function_of_repo_ok_values(tmp_path: Path):
    """
    Portfolio invariant:
    portfolio.ok must equal AND over repo.ok values.
    (This freezes that there is no hidden cross-repo coupling affecting ok.)
    """
    policy = "policies/default.json"

    repos_path = tmp_path / "repos.json"
    repos_path.write_text(
        json.dumps({"repos": [{"id": "self", "path": "."}]}, indent=2, sort_keys=True) + "\n"
    )

    data = _portfolio_run(policy, repos_path)

    repo_oks = [r["ok"] for r in data["repos"]]
    assert data["ok"] == all(repo_oks)


def test_fail_closed_propagation_not_maskable(tmp_path: Path):
    """
    Fail-closed propagation invariant (conditional):
    If any repo indicates fail_closed==True, portfolio.fail_closed must be True and portfolio.ok must be False.
    This does not force a fail-closed scenario; it freezes propagation if one occurs.
    """
    policy = "policies/default.json"

    repos_path = tmp_path / "repos.json"
    repos_path.write_text(
        json.dumps({"repos": [{"id": "self", "path": "."}]}, indent=2, sort_keys=True) + "\n"
    )

    data = _portfolio_run(policy, repos_path)

    any_repo_fail_closed = any(r["fail_closed"] is True for r in data["repos"])
    if any_repo_fail_closed:
        assert data["fail_closed"] is True
        assert data["ok"] is False
