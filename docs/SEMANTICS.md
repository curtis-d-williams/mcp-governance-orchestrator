# Orchestrator Semantics (V1)

## Scope

Repository: curtis-d-williams/mcp-governance-orchestrator  
This document clarifies the meaning of top-level orchestrator fields in the V1 output contract.

This is documentation only:
- No behavior changes
- No schema changes
- No new flags
- No network calls

## Terms

Execution success:
- The orchestrator executed deterministically and produced an output object.
- Guardians were invoked (or skipped) according to the orchestrator’s rules.

Policy success:
- The guardian(s) evaluated the target and reported compliance (ok == true).

Fail-closed:
- A safety posture: when a guardian cannot complete its evaluation reliably, it returns a failing result rather than a permissive one.

## Current Observed Output (V1)

Example evidence is captured in docs/EXAMPLE_OUTPUTS.md (v0.2.3 real deterministic JSON).

Observed:
- Guardian result may report:
    ok: false
    fail_closed: true

- Orchestrator wrapper may report:
    ok: true
    fail_closed: false

## V1 Contract Semantics (As Implemented)

1) Top-level orchestrator ok

Meaning:
- ok indicates orchestrator-level execution success (the wrapper ran and produced output).
- ok does NOT represent aggregate guardian policy success.

Implication:
- Downstream consumers MUST NOT treat orchestrator ok == true as “policy passed”.

2) Top-level orchestrator fail_closed

Meaning:
- fail_closed indicates whether the orchestrator itself fail-closed due to an orchestrator-level inability to operate deterministically.
- fail_closed does NOT automatically elevate a child guardian’s fail_closed state.

Implication:
- fail_closed at the guardian level is authoritative for policy fail-closed behavior.

## Consumer Guidance (CI/CD and Automation)

If your goal is to gate releases on policy compliance:

- Gate on guardian results:
    - If any guardian ok == false, treat the run as policy failure.
    - If any guardian fail_closed == true, treat the run as policy failure with fail-closed posture.

- Do not gate on orchestrator wrapper ok alone.

If your goal is to validate deterministic execution of the orchestrator itself:

- orchestrator ok == true indicates the wrapper executed successfully.
- orchestrator fail_closed == true indicates orchestrator-level fail-closed behavior.

## Open Question (Tracked)

The semantic asymmetry is tracked as a contract clarification discussion:
- GitHub Issue #1: Clarify orchestrator-level ok / fail_closed semantics (V1 contract clarification)

Any behavior/schema change, if desired, is V2-only with explicit migration notes.
