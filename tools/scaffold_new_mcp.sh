#!/usr/bin/env bash
set -euo pipefail

REPO_NAME="${1:-}"
if [[ -z "$REPO_NAME" ]]; then
  echo "usage: $0 <repo-name>"
  exit 2
fi

# Portability:
# - ORCH_ROOT is inferred from this script's location (repo_root/tools/..)
# - BASE defaults to the parent directory of ORCH_ROOT (i.e., where new repos will be created)
# - Override BASE by setting MCP_FACTORY_BASE (absolute path recommended)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORCH_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BASE="${MCP_FACTORY_BASE:-$(cd "$ORCH_ROOT/.." && pwd)}"

SRC="$ORCH_ROOT/templates/guardian_skeleton"
DEST="$BASE/$REPO_NAME"

rm -rf "$DEST"
mkdir -p "$DEST"

rsync -av --exclude ".git" --exclude "temp-mcp-test" "$SRC/" "$DEST/"

cd "$DEST"
git init >/dev/null
git add .
git commit -m "initial scaffold from guardian_skeleton template" >/dev/null

python3 - <<'PY'
import json
from mcp_governance_orchestrator.server import run_guardians

out = run_guardians(
    guardians=["mcp-repo-hygiene-guardian:v1","mcp-release-guardian:v1"],
    repo_path="."
)

ok = out.get("ok")
fc = out.get("fail_closed")
print("ok=", ok, "fail_closed=", fc)
if not ok or fc:
    # print failing checks if present
    for g in out.get("guardians", []):
        og = g.get("output") or {}
        if isinstance(og, dict) and "checks" in og:
            for c in og["checks"]:
                if not c.get("ok", False):
                    print("FAIL:", g["guardian_id"], c["check_id"], "-", c["details"])
    raise SystemExit(1)

open("docs/EXAMPLE_OUTPUTS.md","w",encoding="utf-8").write(
    json.dumps(out, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
)
PY

python3 -m json.tool docs/EXAMPLE_OUTPUTS.md >/dev/null
git add docs/EXAMPLE_OUTPUTS.md
git commit -m "docs: canonical EXAMPLE_OUTPUTS" >/dev/null

echo "DONE: created repo at "
pwd

echo "DONE:"
git log -2 --oneline
