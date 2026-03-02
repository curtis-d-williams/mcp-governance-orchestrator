# Governance Adoption Model (Non-Contract)

Version: Draft 1
Scope: Observability layer only (does not modify portfolio output contract)

## Purpose

The portfolio engine can apply governance to any repository path.

Governance may originate from:
1) A repo-local registry (config/guardians.json)
2) A fallback/default registry supplied by the orchestrator

To measure governance maturity across a portfolio, we define explicit adoption levels.

## Adoption Levels

Level 0 — No Local Registry
Criteria:
- config/guardians.json does not exist in repo
Signal:
- has_repo_registry = false

Level 1 — Local Registry Present
Criteria:
- config/guardians.json exists
Signal:
- has_repo_registry = true

Level 2 — Tier 1 + Tier 2 Policy Compliance
Criteria:
- Portfolio run with default policy returns returncode = 0
Signal:
- Repo-level returncode = 0

Level 3 — Advanced Constraints (Future)
- Requires contract evolution
- Not yet formalized

## Observability Tools

To detect Level 0 vs Level 1:
scripts/portfolio_adoption_report.py --repos <repos.json>

To detect Level 2:
python -m mcp_governance_orchestrator.portfolio run --policy policies/default.json --repos <repos.json>

Important:
Level 0 repositories may still pass Level 2 due to fallback registry behavior.
This is current engine semantics.

## Registry Source (Opt-in)

The portfolio runner can optionally emit registry provenance metadata via:

  --include-registry-source

When enabled, each repo result's `stdout_json` includes:

  registry: { source: "repo" | "fallback", path: "<resolved config/guardians.json path>" }

Default portfolio output remains unchanged unless this flag is supplied.
