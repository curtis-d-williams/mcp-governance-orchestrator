# Governed Autonomous Capability Factory — Invariants

This repository implements a **governed autonomous capability factory** for
Model Context Protocol (MCP) infrastructure.

The factory detects capability gaps, generates MCP server artifacts,
compares them against reference implementations, derives improvement gaps,
and plans capability evolution — all under governance constraints.

This document defines the **invariants** the system must preserve.

---

## Factory Control Loop

The factory operates as a deterministic control loop:

portfolio capability gap
→ governed planner selection
→ capability builder
→ reference MCP comparison
→ gap derivation
→ capability evolution planning
→ evolution execution
→ artifact rebuild
→ ledger update

Each stage must produce deterministic outputs when given identical inputs.

---

## Determinism Invariants

The following outputs must be stable across repeated runs:

Artifact generation  
The builder must produce identical files for identical capability inputs.

Reference comparison  
Comparing a generated MCP server against a reference implementation must
produce identical comparison artifacts.

Gap derivation  
Capability gaps derived from comparison results must be deterministic.

Evolution planning  
Capability evolution plans generated from comparison signals must be
stable across runs.

These guarantees ensure the factory loop behaves predictably and
supports reproducible experimentation.

---

## Governance Invariants

Factory execution is always governed.

Planner execution must be policy-gated.

Capability builders must execute only when a valid capability request
is resolved from planner output or portfolio gap synthesis.

Ledger updates must be auditable and attributable to a specific
factory cycle.

The system must fail closed if governance or artifact generation fails.

---

## Repository Validation Signals

Deterministic behavior is validated through:

- Full pytest suite
- Deterministic builder tests
- Generated artifact SHA baselines
- Stable comparison/gap/plan hashes across repeated runs

These signals verify that the governed autonomous capability factory
remains stable as the repository evolves.

---

## Scope of This Document

This file specifies operational invariants for contributors and reviewers.

It is intentionally concise and should evolve only if the factory control
loop or determinism guarantees change.
