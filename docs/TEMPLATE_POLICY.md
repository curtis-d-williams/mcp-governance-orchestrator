# Template Scaling Policy

This policy governs how the factory may add or evolve templates without creating
policy drift, nondeterminism, or uncontrolled surface area.

The purpose is to scale breadth safely.

---

## Definitions

Template:
A factory input that materializes a new repo skeleton.

Policy Surface:
Anything that can change runtime guardian behavior, output schema, canonicalization,
fail-closed semantics, or composition semantics.

Mechanics Surface:
Repo layout, packaging scaffolding, CI wiring, docs, and non-semantic defaults
that do not alter guardian policy behavior.

---

## Core Rule

Templates may change mechanics freely, but must not change policy.

If a template change could plausibly affect guardian runtime outputs or semantics,
it is a policy change and must be treated as a contract change.

---

## Template Categories (Allowed)

1. guardian_skeleton
   - Minimal deterministic guardian scaffold
   - Canonical JSON plumbing + deterministic test hooks
   - Zero domain policy beyond exemplar checks

2. policy_guardian_template (future)
   - Same contract as guardian_skeleton
   - Adds a narrowly scoped, deterministic rule-set
   - Must document scope + non-goals

3. research_mcp_template (future)
   - Explicitly non-governance; may be excluded from guardian contract set
   - Must declare whether determinism / fail-closed applies

4. intelligence_layer_template (future)
   - Suggestion-only tier
   - Must never merge policy changes without Authority approval + evidence gates

---

## Allowed Changes (Mechanics Only)

- Directory structure
- README / docs / examples (as long as examples remain reproducible)
- CI configuration
- Packaging metadata (non-semantic)
- Base path portability handling
- Evidence artifact automation

---

## Disallowed Changes (Policy)

- Canonical JSON schema fields or ordering
- Canonicalization rules
- Fail-closed semantics
- Determinism requirements
- Guardian invocation contract
- Orchestrator aggregation semantics
- Network calls or nondeterministic dependencies

---

## Required Gates for Any Template Addition

A new template is not considered "added" unless:

1. Invariant Gate
   - No nested `.git` inside templates
   - Factory structural checks pass

2. Determinism Gate
   - Repeated factory runs yield byte-identical outputs
   - Generated guardian runs yield byte-identical canonical JSON

3. Evidence Gate
   - EXAMPLE_OUTPUTS committed
   - Regeneration steps documented and reproducible

4. CI Gate
   - Required workflows pass on generated repo and factory repo (when applicable)

---

## Versioning Rule

If and only if a change touches policy surface:

- It must be explicitly documented as a contract change
- It must be version-bounded (major/minor per your scheme)
- It must regenerate example artifacts
- It must include a migration note

Otherwise:
- Treat as a mechanics-only change (patch-level)

---

## Authority Constraint

Executors (agents) may create repos from templates and regenerate evidence.

Executors may not modify templates beyond mechanics without Authority approval.

If uncertain whether a change is policy, stop and escalate.