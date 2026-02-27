# mcp-governance-orchestrator — Canonical Example Outputs (V1)

These examples reflect the current V1 implementation, where guardian wiring is intentionally stubbed.

Notes:
- Input guardian order is preserved.
- Known guardians are not invoked in V1 and return deterministic fail-closed stubs.
- Unknown guardians fail-closed.

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

## Example 3 — Known guardian (stubbed wiring)

Input:
- repo_path: /repos/example
- guardians: ["mcp-policy-guardian:v1"]

Output:
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
      "details": "fail-closed: guardian_not_wired"
    }
  ]
}
