# SPDX-License-Identifier: MIT
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple


@dataclass(frozen=True)
class RepoSpec:
    id: str
    path: str


def _canon(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _load_repos_file(path: str) -> Tuple[List[RepoSpec], Dict[str, Any] | None]:
    p = Path(path)
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return [], {
            "error_type": "portfolio_load",
            "errors": [{"path": "$.repos", "type": "load_error", "message": str(e)}],
        }

    if not isinstance(raw, dict) or "repos" not in raw:
        return [], {
            "error_type": "portfolio_schema",
            "errors": [{"path": "$", "type": "schema", "message": "expected object with key 'repos'"}],
        }

    repos_val = raw.get("repos")
    if not isinstance(repos_val, list):
        return [], {
            "error_type": "portfolio_schema",
            "errors": [{"path": "$.repos", "type": "schema", "message": "expected list[object]"}],
        }

    repos: List[RepoSpec] = []
    errors: List[Dict[str, str]] = []
    for i, item in enumerate(repos_val):
        if not isinstance(item, dict):
            errors.append({"path": f"$.repos[{i}]", "type": "schema", "message": "expected object"})
            continue
        rid = item.get("id")
        rpath = item.get("path")
        if not isinstance(rid, str) or not rid.strip():
            errors.append({"path": f"$.repos[{i}].id", "type": "schema", "message": "expected non-empty string"})
        if not isinstance(rpath, str) or not rpath.strip():
            errors.append({"path": f"$.repos[{i}].path", "type": "schema", "message": "expected non-empty string"})
        if isinstance(rid, str) and rid.strip() and isinstance(rpath, str) and rpath.strip():
            repos.append(RepoSpec(id=rid.strip(), path=rpath.strip()))

    if errors:
        return [], {"error_type": "portfolio_schema", "errors": errors}

    # Deterministic order
    repos_sorted = sorted(repos, key=lambda r: (r.id, r.path))
    return repos_sorted, None


def _run_repo(policy_path: str, repo: RepoSpec) -> Dict[str, Any]:
    cmd = [
        sys.executable,
        "-m",
        "mcp_governance_orchestrator.registry",
        "run-policy",
        policy_path,
        repo.path,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)

    stdout = (r.stdout or "").strip()
    stderr = (r.stderr or "").strip()

    parsed: Any = None
    parse_ok = False
    if stdout:
        try:
            parsed = json.loads(stdout)
            parse_ok = True
        except Exception:
            parsed = None
            parse_ok = False

    # Best-effort: derive ok/fail_closed from parsed output when available.
    ok = (r.returncode == 0)
    fail_closed = (r.returncode != 0)

    if parse_ok and isinstance(parsed, dict):
        # If it looks like the combined envelope, honor those fields.
        if "ok" in parsed and isinstance(parsed.get("ok"), bool):
            ok = bool(parsed["ok"])
        if "fail_closed" in parsed and isinstance(parsed.get("fail_closed"), bool):
            fail_closed = bool(parsed["fail_closed"])

    return {
        "id": repo.id,
        "path": repo.path,
        "returncode": int(r.returncode),
        "ok": bool(ok),
        "fail_closed": bool(fail_closed),
        "stdout_json": parsed if parse_ok else None,
        "stdout_raw": stdout if not parse_ok else "",
        "stderr": stderr,
    }


def portfolio_run(policy_path: str, repos_path: str) -> Tuple[Dict[str, Any], int]:
    repos, err = _load_repos_file(repos_path)
    if err is not None:
        out = {
            "tool": "portfolio_run",
            "ok": False,
            "fail_closed": True,
            "error": err,
            "policy_path": policy_path,
            "repos_path": repos_path,
        }
        return out, 3

    repo_results: List[Dict[str, Any]] = []
    seen_rc = set()

    for repo in repos:
        res = _run_repo(policy_path, repo)
        repo_results.append(res)
        seen_rc.add(res["returncode"])

    # Aggregate status
    any_rc3 = 3 in seen_rc
    any_nonzero = any(rc != 0 for rc in seen_rc)

    if any_rc3:
        exit_code = 3
    elif any_nonzero:
        exit_code = 2
    else:
        exit_code = 0

    summary = {
        "repos_total": len(repo_results),
        "repos_ok": sum(1 for r in repo_results if r.get("returncode") == 0),
        "repos_failed": sum(1 for r in repo_results if r.get("returncode") != 0),
        "repos_schema_or_load_errors": sum(1 for r in repo_results if r.get("returncode") == 3),
    }

    out = {
        "tool": "portfolio_run",
        "ok": (exit_code == 0),
        "fail_closed": (exit_code != 0),
        "policy_path": policy_path,
        "repos_path": repos_path,
        "repos": repo_results,
        "summary": summary,
    }
    return out, exit_code


def _usage() -> str:
    return (
        "usage:\n"
        "  python -m mcp_governance_orchestrator.portfolio run --policy <policy.json> --repos <repos.json>\n"
    )


def main(argv: List[str] | None = None) -> int:
    argv = list(argv or sys.argv[1:])
    if not argv or argv[0] in ("-h", "--help", "help"):
        sys.stdout.write(_usage())
        return 0

    cmd = argv.pop(0)
    if cmd != "run":
        sys.stdout.write(_usage())
        return 3

    policy_path = None
    repos_path = None
    while argv:
        tok = argv.pop(0)
        if tok == "--policy" and argv:
            policy_path = argv.pop(0)
        elif tok == "--repos" and argv:
            repos_path = argv.pop(0)
        else:
            sys.stdout.write(_usage())
            return 3

    if not policy_path or not repos_path:
        sys.stdout.write(_usage())
        return 3

    out, code = portfolio_run(policy_path=policy_path, repos_path=repos_path)
    sys.stdout.write(_canon(out) + "\n")
    return int(code)


if __name__ == "__main__":
    raise SystemExit(main())
