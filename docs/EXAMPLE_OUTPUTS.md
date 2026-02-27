### Real E2E Example Output — v0.2.2 (Placeholder)

This section demonstrates deterministic JSON output from \`mcp-governance-orchestrator\` with the \`release_guardian\` optional extra.
Currently using v0.2.1 deterministic template as placeholder for v0.2.2.

\`\`\`json
{
  "tool": "run_guardians",
  "repo_path": "/repos/example",
  "ok": true,
  "fail_closed": false,
  "guardians": [
    {
      "guardian_id": "mcp-release-guardian:v1",
      "invoked": true,
      "ok": true,
      "fail_closed": false,
      "output": {
        "tool": "check_repo_hygiene",
        "ok": true,
        "details": "all release checks passed"
      },
      "details": ""
    }
  ]
}
\`\`\`
