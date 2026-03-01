# Example Outputs

This file contains literal, deterministic JSON outputs captured from
real runs, intended for copy/paste verification.

## v0.2.2 (historical) --- placeholder only

```json
{"placeholder":true,"note":"v0.2.2 did not produce a matching build artifact; real deterministic JSON captured starting in v0.2.3"}
```

## v0.2.3 (historical) — pre Tier 2 ok/fail_closed propagation

```json
{"fail_closed":false,"guardians":[{"details":"","fail_closed":false,"guardian_id":"mcp-release-guardian:v1","invoked":true,"ok":true,"output":{"checks":[{"check_id":"has_package_definition","details":"Found pyproject.toml","ok":true},{"check_id":"has_license","details":"Found LICENSE","ok":true},{"check_id":"has_readme","details":"Found README.md","ok":true},{"check_id":"has_bug_report_template","details":"Not found: .github/ISSUE_TEMPLATE/bug_report.yml","ok":false},{"check_id":"has_ci_workflows","details":"Found .github/workflows/","ok":true},{"check_id":"has_v1_contract","details":"Found docs/V1_CONTRACT.md","ok":true},{"check_id":"has_determinism_notes","details":"Not found: docs/DETERMINISM_NOTES.md","ok":false}],"fail_closed":true,"ok":false,"repo_path":"/Users/Curtis/Documents/GitHub_Repos/mcp-governance-orchestrator","tool":"check_repo_hygiene"}}],"ok":true,"repo_path":".","tool":"run_guardians"}
```

## Tier 2 composition — two guardians (release + repo hygiene)

```json
{"fail_closed":true,"guardians":[{"details":"","fail_closed":true,"guardian_id":"mcp-release-guardian:v1","invoked":true,"ok":false,"output":{"checks":[{"check_id":"has_package_definition","details":"Found pyproject.toml","ok":true},{"check_id":"has_license","details":"Found LICENSE","ok":true},{"check_id":"has_readme","details":"Found README.md","ok":true},{"check_id":"has_bug_report_template","details":"Not found: .github/ISSUE_TEMPLATE/bug_report.yml","ok":false},{"check_id":"has_ci_workflows","details":"Found .github/workflows/","ok":true},{"check_id":"has_v1_contract","details":"Found docs/V1_CONTRACT.md","ok":true},{"check_id":"has_determinism_notes","details":"Not found: docs/DETERMINISM_NOTES.md","ok":false}],"fail_closed":true,"ok":false,"repo_path":"/Users/Curtis/Documents/GitHub_Repos/mcp-governance-orchestrator","tool":"check_repo_hygiene"}},{"details":"","fail_closed":false,"guardian_id":"mcp-repo-hygiene-guardian:v1","invoked":true,"ok":true,"output":{"details":"ok","fail_closed":false,"ok":true,"output":{"missing_required_files":[],"notes":[],"tracked_build_artifacts":[]},"repo_path":".","tool":"check_repo_hygiene"}}],"ok":false,"repo_path":".","tool":"run_guardians"}
```

## v0.3.2 — Tier 2 composition (repo hygiene + license header) against this repo (expected fail-closed)

Note: This repo currently fail-closes `mcp-license-header-guardian:v1` because some tracked `.py` files do not include `SPDX-License-Identifier` (or `Copyright`) within the first 5 lines.

```json
{"fail_closed":true,"guardians":[{"details":"","fail_closed":false,"guardian_id":"mcp-repo-hygiene-guardian:v1","invoked":true,"ok":true,"output":{"details":"ok","fail_closed":false,"ok":true,"output":{"missing_required_files":[],"notes":[],"tracked_build_artifacts":[]},"repo_path":".","tool":"check_repo_hygiene"}},{"details":"","fail_closed":true,"guardian_id":"mcp-license-header-guardian:v1","invoked":true,"ok":false,"output":{"details":"fail-closed: missing_license_header","fail_closed":true,"ok":false,"output":{"files_missing_header":["src/mcp_governance_orchestrator/__init__.py","src/mcp_governance_orchestrator/server.py","tests/test_tier2_propagation.py","tests/test_tools.py"],"notes":["scope: tracked .py files only","rule: first 5 lines contain Copyright OR SPDX-License-Identifier","listing: git ls-files"]},"repo_path":".","tool":"check_license_header"}}],"ok":false,"repo_path":".","tool":"run_guardians"}
```
