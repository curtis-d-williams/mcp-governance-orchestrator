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
