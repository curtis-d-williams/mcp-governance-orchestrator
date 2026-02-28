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

See docs/SEMANTICS.md for the V1 meaning of orchestrator-level ok/fail_closed (execution vs policy semantics) and consumer gating guidance.

``` json
{"fail_closed":false,"guardians":[{"details":"","fail_closed":false,"guardian_id":"mcp-release-guardian:v1","invoked":true,"ok":true,"output":{"checks":[{"check_id":"has_package_definition","details":"Found pyproject.toml","ok":true},{"check_id":"has_license","details":"Found LICENSE","ok":true},{"check_id":"has_readme","details":"Found README.md","ok":true},{"check_id":"has_bug_report_template","details":"Not found: .github/ISSUE_TEMPLATE/bug_report.yml","ok":false},{"check_id":"has_ci_workflows","details":"Found .github/workflows/","ok":true},{"check_id":"has_v1_contract","details":"Found docs/V1_CONTRACT.md","ok":true},{"check_id":"has_determinism_notes","details":"Not found: docs/DETERMINISM_NOTES.md","ok":false}],"fail_closed":true,"ok":false,"repo_path":"/Users/Curtis/Documents/GitHub_Repos/mcp-governance-orchestrator","tool":"check_repo_hygiene"}}],"ok":true,"repo_path":".","tool":"run_guardians"}
```

---


## Tier 2 composition: two guardians (multi-guardian orchestration)

**Goal:** Produce deterministic composition evidence by running two guardians under a clean-room venv and capturing canonical JSON output.

**Semantics:** See docs/SEMANTICS.md.

### Prerequisites (clean-room venv)

Pinned installs:

- mcp-governance-orchestrator (editable local repo)
- mcp-release-guardian==0.1.4
- mcp-dependency-integrity-guardian (editable local repo; tag v0.1.1)

### Run (two guardians)

Guardians (order preserved):

- mcp-release-guardian:v1
- mcp-dependency-integrity-guardian:v1

### Routing note (V1)

The orchestrator uses a V1 in-process static routing table (GUARDIAN_ROUTING_TABLE) to map guardian_id to an import path + callable.

For guardians whose native output does not include the required "tool" key, the orchestrator uses a deterministic adapter callable that adds "tool" and preserves the guardian output verbatim under a nested key.

### Canonical JSON output (deterministic)

```json
{"fail_closed":false,"guardians":[{"details":"","fail_closed":false,"guardian_id":"mcp-release-guardian:v1","invoked":true,"ok":true,"output":{"checks":[{"check_id":"has_package_definition","details":"Found pyproject.toml","ok":true},{"check_id":"has_license","details":"Found LICENSE","ok":true},{"check_id":"has_readme","details":"Found README.md","ok":true},{"check_id":"has_bug_report_template","details":"Not found: .github/ISSUE_TEMPLATE/bug_report.yml","ok":false},{"check_id":"has_ci_workflows","details":"Found .github/workflows/","ok":true},{"check_id":"has_v1_contract","details":"Found docs/V1_CONTRACT.md","ok":true},{"check_id":"has_determinism_notes","details":"Not found: docs/DETERMINISM_NOTES.md","ok":false}],"fail_closed":true,"ok":false,"repo_path":"/Users/Curtis/Documents/GitHub_Repos/mcp-governance-orchestrator","tool":"check_repo_hygiene"}},{"details":"","fail_closed":false,"guardian_id":"mcp-dependency-integrity-guardian:v1","invoked":true,"ok":true,"output":{"output":{"checks":[{"check_id":"python_requirements_present","kind":"file_present","path":"requirements.txt","present":false},{"check_id":"python_poetry_lock_present","kind":"file_present","path":"poetry.lock","present":false},{"check_id":"node_package_json_present","kind":"file_present","path":"package.json","present":false},{"check_id":"node_package_lock_present","kind":"file_present","path":"package-lock.json","present":false},{"check_id":"node_pnpm_lock_present","kind":"file_present","path":"pnpm-lock.yaml","present":false},{"check_id":"node_yarn_lock_present","kind":"file_present","path":"yarn.lock","present":false},{"check_id":"python_requirements_pins","kind":"requirements_pins","note":"requirements.txt not present; pinning check skipped","ok":true,"path":"requirements.txt","present":false,"unpinned":[]}],"fail_closed":false,"guardian":"mcp-dependency-integrity-guardian:v1","ok":false},"repo_path":".","tool":"check_dependency_integrity"}}],"ok":true,"repo_path":".","tool":"run_guardians"}
```

### Determinism check

- SHA256(run1)=778773208a1635e7aa5693e05f12e4f6c1201a5328cfd563349a8cebc60a1bd4
- SHA256(run2)=778773208a1635e7aa5693e05f12e4f6c1201a5328cfd563349a8cebc60a1bd4

### Consumer aggregation (V1; no schema changes)

- policy_ok = ALL(guardian.ok == true)
- policy_fail_closed = ANY(guardian.fail_closed == true)
- execution_ok = orchestrator.ok
- execution_fail_closed = orchestrator.fail_closed
