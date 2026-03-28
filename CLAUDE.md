# mcp-governance-orchestrator

This repository implements a **governed autonomous capability factory** for MCP infrastructure synthesis and governed software generation workflows.

## Repository identity and fixed architecture

These are non-negotiable:

- Preserve the implemented Phase G architecture.
- Preserve the canonical governed pipeline:

  planner -> builder -> synthesis_event -> cycle artifact -> cycle-history aggregation -> capability_effectiveness_ledger -> planner learning adjustments

- Preserve the canonical governed build path:

  planner/runtime -> factory_pipeline -> build_capability_artifact -> artifact_registry -> builder

- `factory_pipeline.py` is the sole execution seam.
- `builder/mcp_builder.py` is the canonical deterministic MCP builder.
- `scripts/generate_mcp_server.py` must remain a thin developer-facing entrypoint that delegates to the canonical builder only.
- Do not redesign architecture.
- Do not re-derive architecture from scratch.
- Do not introduce a parallel subsystem.
- Do not revive Phase H.

## Terminology

- Use the term **governed autonomous capability factory**.
- Avoid the term **MCP factory** unless quoting historical text.

## Agent role map

This repo uses three agents maximum:

- `main-orchestrator`
- `worker`
- `reviewer`

### Main Orchestrator
The Main Orchestrator:
- controls checkpoint flow
- preserves governance discipline
- routes approvals
- translates subordinate findings into concise governance summaries

### Worker
The Worker:
- performs bounded inspection
- performs bounded implementation when approved
- runs targeted validation when approved

### Reviewer
The Reviewer:
- performs bounded diff and validation assessment when approved
- states commit readiness as a factual technical posture

## High-level workflow pattern

For implementation work, the default pattern is:

1. inspect bounded candidate
2. approve bounded work
3. implement plus targeted tests
4. approve validation
5. reviewer summary
6. approve commit

For execution-only tasks with no source edits and no commit, the default pattern is:

1. identify bounded candidate
2. inspect execution preconditions and exact command plan
3. approve execution plan
4. execute approved command(s)
5. report result and stop

If scope expands materially, stop and re-enter governance flow at the proper approval point.

## Global repo-wide constraints

- Do not reinterpret fixed architecture.
- Do not treat runtime-written or generated artifacts as commit-ready by default.
- Worker and Reviewer do not route approval.
- Governed evidence must reflect actual approved execution and validation only.
- Preserve minimal diffs, explicit approvals, and narrow test-backed changes.
- If Curtis is driving locally, give exactly one terminal command at a time.
- Memory writes are prohibited after any PAUSE, STOP, or task close instruction unless separately and explicitly approved.

## File authority and precedence

- `CLAUDE.md` provides repo-wide identity and shared constraints.
- `.claude/agents/main-orchestrator.md` governs checkpoint flow and approval routing.
- `.claude/agents/worker.md` governs Worker dispatch, scope, inspection, and implementation behavior.
- `.claude/agents/reviewer.md` governs Reviewer assessment and evidence reporting.

When a role-specific file is more specific, it controls that role’s behavior.

## Session continuity

Use `.claude/session_log.md` only as concise continuity support.

It may record:
- current objective
- last approved plan
- files inspected
- files changed
- tests run
- repo state
- open risks
- next recommended step

Treat the session log as working state, not as a substitute for checkpoint discipline.

## Default bias

Bias toward:
- preserving the canonical governed pipeline
- preserving the canonical build path
- minimal diffs
- explicit approvals
- narrow, test-backed changes
- continuation from known architecture rather than rediscovery
