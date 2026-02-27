# mcp-governance-orchestrator — Canonical Example Outputs (V1)

Notes:
- Input guardian order is preserved.
- Known guardians are invoked in-process via the static routing table; outputs embedded verbatim.
- `ok` and `fail_closed` on each guardian entry are orchestrator-owned (not read from guardian output).
- Unknown guardians and all invocation failures are fail-closed with deterministic error codes.

---

## Example 1 — Empty guardians (fail-closed)

Input:
- repo_path: /repos/example
- guardians: []

Output:
{
  "tool": "run_guardians",
  "repo_path": "/repos/example",
  "ok": false,
  "fail_closed": true,
  "guardians": [
    {
      "guardian_id": "",
      "invoked": false,
      "ok": false,
      "fail_closed": true,
      "output": null,
      "details": "fail-closed: guardians_empty"
    }
  ]
}

---

## Example 2 — Unknown guardian ID

Input:
- repo_path: /repos/example
- guardians: ["unknown:v1"]

Output:
{
  "tool": "run_guardians",
  "repo_path": "/repos/example",
  "ok": false,
  "fail_closed": true,
  "guardians": [
    {
      "guardian_id": "unknown:v1",
      "invoked": false,
      "ok": false,
      "fail_closed": true,
      "output": null,
      "details": "fail-closed: guardian_unknown"
    }
  ]
}

---

## Example 3 — Known guardian, successful invocation (invoked=true)

Input:
- repo_path: /repos/example
- guardians: ["mcp-policy-guardian:v1"]

Output (guardian package installed and callable returns valid output):
{
  "tool": "run_guardians",
  "repo_path": "/repos/example",
  "ok": true,
  "fail_closed": false,
  "guardians": [
    {
      "guardian_id": "mcp-policy-guardian:v1",
      "invoked": true,
      "ok": true,
      "fail_closed": false,
      "output": {
        "tool": "check_repo_policy",
        "ok": true,
        "details": "all policy checks passed"
      },
      "details": ""
    }
  ]
}

---

## Example 4 — Known guardian, import failure (fail-closed)

Input:
- repo_path: /repos/example
- guardians: ["mcp-policy-guardian:v1"]

Output (guardian package not installed):
{
  "tool": "run_guardians",
  "repo_path": "/repos/example",
  "ok": false,
  "fail_closed": true,
  "guardians": [
    {
      "guardian_id": "mcp-policy-guardian:v1",
      "invoked": false,
      "ok": false,
      "fail_closed": true,
      "output": null,
      "details": "fail-closed: guardian_import_failed"
    }
  ]
}
## Real E2E Example Output — v0.2.1

This example demonstrates a clean installation and verification of `mcp-governance-orchestrator` with the `release_guardian` optional extra in a new virtual environment.

\`\`\`bash
# 1️⃣ Create a clean temporary venv
rm -rf /tmp/mgo_e2e_021
python3 -m venv /tmp/mgo_e2e_021
source /tmp/mgo_e2e_021/bin/activate
python -m pip install -U pip
python -V
python -m pip -V

# 2️⃣ Download the v0.2.1 source release
mkdir -p /tmp/mgo_release
cd /tmp/mgo_release
curl -L -O https://github.com/curtis-d-williams/mcp-governance-orchestrator/archive/refs/tags/v0.2.1.tar.gz

# 3️⃣ Install the orchestrator
python -m pip install /tmp/mgo_release/v0.2.1.tar.gz
python -m pip show mcp-governance-orchestrator

# 4️⃣ Install the release guardian
python -m pip install "mcp-release-guardian==0.1.4"
python -m pip show mcp-release-guardian
\`\`\`

### Expected Output
\`\`\`text
# python -m pip show mcp-governance-orchestrator
# Name: mcp-governance-orchestrator
# Version: 0.2.1
# Summary: Deterministic MCP server for validating repository policy governance artifacts
# Location: /private/tmp/mgo_e2e_021/lib/python3.13/site-packages
# Requires: fastmcp

# python -m pip show mcp-release-guardian
# Name: mcp-release-guardian
# Version: 0.1.4
# Summary: Deterministic MCP server for validating release hygiene in local repositories
# Location: /private/tmp/mgo_e2e_021/lib/python3.13/site-packages
# Requires: fastmcp
\`\`\`

