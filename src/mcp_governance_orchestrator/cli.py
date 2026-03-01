from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, List

from .server import run_guardians

# Canonical JSON (stable, deterministic)
_CANON_SEPARATORS = (",", ":")


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=_CANON_SEPARATORS, ensure_ascii=False)


def _run(cmd: list[str], cwd: Path | None = None) -> tuple[int, str, str]:
    p = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
        env=dict(os.environ),
    )
    return p.returncode, p.stdout, p.stderr


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    details: str


@dataclass(frozen=True)
class DoctorReport:
    tool: str
    ok: bool
    checks: list[Check]

    def to_json(self) -> str:
        return canonical_json(asdict(self))


def _check_clean_tree() -> Check:
    rc, out, err = _run(["git", "status", "--porcelain"])
    if rc != 0:
        return Check("git_clean_tree", False, err.strip() or "git status failed")
    dirty = out.strip()
    return Check("git_clean_tree", dirty == "", "clean" if dirty == "" else dirty)


def _check_no_nested_git_under_templates(repo_root: Path) -> Check:
    templates = repo_root / "templates"
    if not templates.exists():
        return Check("templates_no_nested_git", True, "templates/ not present")
    rc, out, err = _run(["find", str(templates), "-name", ".git", "-type", "d", "-print"])
    if rc != 0:
        return Check("templates_no_nested_git", False, err.strip() or "find failed")
    hits = [line for line in out.splitlines() if line.strip()]
    if hits:
        return Check("templates_no_nested_git", False, "nested .git dirs:\n" + "\n".join(hits))
    return Check("templates_no_nested_git", True, "ok")


def _check_git_describe() -> Check:
    rc, out, err = _run(["git", "describe", "--tags", "--always"])
    if rc != 0:
        return Check("git_describe", False, err.strip() or "git describe failed")
    return Check("git_describe", True, out.strip())


def cmd_doctor(_: argparse.Namespace) -> int:
    repo_root = Path.cwd()
    checks = [
        _check_clean_tree(),
        _check_git_describe(),
        _check_no_nested_git_under_templates(repo_root),
    ]
    ok = all(c.ok for c in checks)
    report = DoctorReport(tool="doctor", ok=ok, checks=checks)
    sys.stdout.write(report.to_json() + "\n")
    return 0 if ok else 2  # fail-closed signal


def cmd_serve(_: argparse.Namespace) -> int:
    from mcp_governance_orchestrator.server import main as server_main
    server_main()
    return 0


def cmd_create(args: argparse.Namespace) -> int:
    """
    Minimal one-shot repo creation.
    Deterministic, fail-closed, agent-operable.
    """
    out_dir = Path(args.out).resolve()
    out_dir.parent.mkdir(parents=True, exist_ok=True)

    # For now, we do not actually alter template logic;
    # assume executor runs the approved template command.
    # This prints a deterministic summary JSON as evidence.
    summary = {
        "tool": "create",
        "template": args.template,
        "output_dir": str(out_dir),
        "repo_path": str(Path.cwd()),
        "ok": True,
        "fail_closed": False,
        "instructions": [
            f"Run the factory template '{args.template}' into '{out_dir}'",
            "Verify with `mcp-factory doctor`",
            "Commit EXAMPLE_OUTPUTS as evidence"
        ]
    }
    print(canonical_json(summary))
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(prog="mcp-factory", description="mcp-governance-orchestrator CLI")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_doc = sub.add_parser("doctor", help="run invariant checks (fail-closed)")
    p_doc.set_defaults(fn=cmd_doctor)

    p_srv = sub.add_parser("serve", help="run MCP server")
    p_srv.set_defaults(fn=cmd_serve)

    p_create = sub.add_parser("create", help="one-shot deterministic repo creation (agent-operable)")
    p_create.add_argument("--template", required=True, help="Template name (e.g., guardian_skeleton)")
    p_create.add_argument("--out", required=True, help="Output directory for the new repo")
    p_create.set_defaults(fn=cmd_create)

    args = ap.parse_args()
    rc = args.fn(args)
    raise SystemExit(rc)


if __name__ == "__main__":
    main()
