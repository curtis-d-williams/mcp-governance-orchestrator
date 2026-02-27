# Example Outputs

This file contains literal, deterministic JSON outputs captured from
real runs, intended for copy/paste verification.

## v0.2.2 (historical) --- placeholder only

The v0.2.2 tag was a docs-only adoption hook and did not produce a build
artifact whose package version matched 0.2.2. The JSON below is retained
only for historical continuity.

``` json
{
  "placeholder": true,
  "note": "v0.2.2 did not produce a matching build artifact; real deterministic JSON captured starting in v0.2.3"
}
```

## v0.2.3 --- real deterministic JSON (mcp-release-guardian:v1)

Capture environment:

-   Installed: mcp-governance-orchestrator==0.2.3
NOTE: This example requires mcp-release-guardian==0.1.4 installed in the environment. If not installed, the orchestrator will fail-close with details: fail-closed: guardian_import_failed.

-   Installed: mcp-release-guardian==0.1.4
-   Invocation: Python one-shot via
    `from mcp_governance_orchestrator.server import run_guardians`
-   Repo path passed to orchestrator: `.` (repo root)

Literal JSON stdout:

``` json

See docs/SEMANTICS.md for the V1 meaning of orchestrator-level ok/fail_closed (execution vs policy semantics) and consumer gating guidance.
{"fail_closed":false,"guardians":[{"details":"","fail_closed":false,"guardian_id":"mcp-release-guardian:v1","invoked":true,"ok":true,"output":{"checks":[{"check_id":"has_package_definition","details":"Found pyproject.toml","ok":true},{"check_id":"has_license","details":"Found LICENSE","ok":true},{"check_id":"has_readme","details":"Found README.md","ok":true},{"check_id":"has_bug_report_template","details":"Not found: .github/ISSUE_TEMPLATE/bug_report.yml","ok":false},{"check_id":"has_ci_workflows","details":"Found .github/workflows/","ok":true},{"check_id":"has_v1_contract","details":"Found docs/V1_CONTRACT.md","ok":true},{"check_id":"has_determinism_notes","details":"Not found: docs/DETERMINISM_NOTES.md","ok":false}],"fail_closed":true,"ok":false,"repo_path":"/Users/Curtis/Documents/GitHub_Repos/mcp-governance-orchestrator","tool":"check_repo_hygiene"}}],"ok":true,"repo_path":".","tool":"run_guardians"}
```
