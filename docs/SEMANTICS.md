# Orchestrator Semantics (V1)

## Scope

Repository: curtis-d-williams/mcp-governance-orchestrator

This document clarifies the meaning of top-level orchestrator fields in the V1 output contract.

This is documentation only:
- No schema changes
- No network calls

## Terms

Execution success:
- The orchestrator executed deterministically and produced an output object.

Policy success:
- The guardian(s) evaluated the target and reported compliance (ok == true).

Fail-closed:
- A safety posture: when a guardian cannot complete its evaluation reliably, it returns a failing result rather than a permissive one.

## V1 Contract Semantics (As Implemented)

### 1) Per-guardian result fields

- invoked indicates whether the guardian callable was invoked.
- output preserves the guardian output verbatim (no normalization).
- ok and fail_closed are propagated from the guardian output fields:
  - ok must be a boolean
  - fail_closed must be a boolean
  - if either is missing or not boolean, the orchestrator marks that guardian result as fail-closed: guardian_output_invalid

### 2) Top-level orchestrator fields

Top-level aggregation is policy-driven:

- ok = ALL(guardian.ok == true) across all guardians in the run
- fail_closed = (not ok) OR ANY(guardian.fail_closed == true)

This matches the Tier 2 consumer aggregation model.

## Consumer Guidance (CI/CD and Automation)

If your goal is to gate releases on policy compliance:

- Gate on top-level:
  - if ok == false, treat the run as policy failure
  - if fail_closed == true, treat the run as policy failure with fail-closed posture

Canonical example outputs are captured in docs/EXAMPLE_OUTPUTS.md.
