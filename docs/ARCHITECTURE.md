# Architecture Model

The MCP Automation Factory operates across three contract-bound layers.

---

# Layer A — Factory (Mechanics)

Responsibilities:

- Template materialization
- Portable base path handling
- Structural invariant enforcement
- Evidence artifact capture
- Deterministic scaffold validation
- CI guardrails

Contract:

The factory produces a repository that passes structural invariants
and contains reproducible evidence hooks.

The factory may not alter guardian semantics.

---

# Layer B — Guardians (Policy)

Responsibilities:

- Deterministic analysis
- Canonical JSON output
- Fail-closed behavior
- No network dependence
- No nondeterminism

Contract:

Given a repository state, a guardian must produce a canonical,
deterministic, fail-closed judgment.

Output schema is stable and versioned.

---

# Layer C — Orchestrator (Composition)

Responsibilities:

- Multi-guardian invocation
- Canonical aggregation semantics
- Fail-closed propagation

Canonical Aggregation Model:

policy_ok = ALL(guardian.ok == true)
policy_fail_closed = ANY(guardian.fail_closed == true)
execution_ok = orchestrator.ok
execution_fail_closed = orchestrator.fail_closed

Contract:

The orchestrator must not mask guardian failure.
Aggregation semantics are stable and versioned.

---

# Constitutional Invariants

These properties may not change without explicit authority approval:

- Canonical JSON ordering
- Fail-closed semantics
- Deterministic outputs
- Guardian isolation
- Evidence reproducibility
- No nested `.git` inside templates

Any violation requires explicit version boundary and documentation.