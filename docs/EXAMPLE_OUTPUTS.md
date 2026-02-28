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

### Note on routing (V1)

The orchestrator uses a V1 in-process static routing table (GUARDIAN_ROUTING_TABLE) to map guardian_id to an import path + callable.

If a guardian_id is not mapped, the orchestrator deterministically fail-closes that guardian with fail-closed: guardian_unknown (no import attempted).

Therefore, even when the dependency-integrity guardian package is installed, it will not be invoked until it is explicitly mapped in the routing table (a code change; out of scope for this docs-only proof).

### Canonical JSON output (deterministic)

```json
{"fail_closed":true,"guardians":[{"details":"","fail_closed":false,"guardian_id":"mcp-release-guardian:v1","invoked":true,"ok":true,"output":{"checks":[{"check_id":"has_package_definition","details":"Found pyproject.toml","ok":true},{"check_id":"has_license","details":"Found LICENSE","ok":true},{"check_id":"has_readme","details":"Found README.md","ok":true},{"check_id":"has_bug_report_template","details":"Not found: .github/ISSUE_TEMPLATE/bug_report.yml","ok":false},{"check_id":"has_ci_workflows","details":"Found .github/workflows/","ok":true},{"check_id":"has_v1_contract","details":"Found docs/V1_CONTRACT.md","ok":true},{"check_id":"has_determinism_notes","details":"Not found: docs/DETERMINISM_NOTES.md","ok":false}],"fail_closed":true,"ok":false,"repo_path":"/Users/Curtis/Documents/GitHub_Repos/mcp-governance-orchestrator","tool":"check_repo_hygiene"}},{"details":"fail-closed: guardian_unknown","fail_closed":true,"guardian_id":"mcp-dependency-integrity-guardian:v1","invoked":false,"ok":false,"output":null}],"ok":false,"repo_path":".","tool":"run_guardians"}
```

### Determinism check

Two repeated runs produced byte-identical output:

- SHA256(run1)=7c5e6814150cb8c23cd948b4aecfaf33f8ab0bca4b3b3e832dfc6a71dc45f9b8
- SHA256(run2)=7c5e6814150cb8c23cd948b4aecfaf33f8ab0bca4b3b3e832dfc6a71dc45f9b8

### Consumer aggregation (V1; no schema changes)

- policy_ok = ALL(guardian.ok == true)
- policy_fail_closed = ANY(guardian.fail_closed == true)
- execution_ok = orchestrator.ok
- execution_fail_closed = orchestrator.fail_closed

