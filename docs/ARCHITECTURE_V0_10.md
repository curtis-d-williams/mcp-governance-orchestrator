# MCP Automation Factory
## Architecture — v0.10.0-alpha

### System Overview

The repository implements a deterministic, regression-protected automation factory that continuously improves task prioritization based on observed outcomes.

The architecture is composed of five layers.

---

# 1. Tier-3 Execution Layer

Runs portfolio tasks and produces deterministic artifacts.

Scripts:

scripts/run_portfolio_task.py  
scripts/aggregate_multi_run_envelopes.py  
scripts/tier3_generate_report.py  

Primary outputs:

tier3_portfolio_report.csv  
tier3_multi_run_aggregate.json  

Purpose:

- execute portfolio tasks safely  
- generate deterministic artifacts  
- provide input signals for higher layers  

---

# 2. Artifact Bridge

Converts Tier-3 artifacts into normalized signals for the control plane.

Script:

scripts/build_portfolio_state_from_artifacts.py

Consumes:

tier3_portfolio_report.csv  
tier3_multi_run_aggregate.json  

Produces:

portfolio_state.json

Normalized signals per repo:

repo_id  
last_run_ok  
artifact_completeness  
determinism_ok  
recent_failures  
stale_runs  

---

# 3. Portfolio Control Plane

Computes portfolio health and generates recommended actions.

Core module:

src/mcp_governance_orchestrator/portfolio_state.py

Builder:

scripts/build_portfolio_state.py

Outputs:

portfolio_state.json

Contains:

- repo status  
- health score  
- risk classification  
- open issues  
- recommended actions  
- portfolio summary  

---

# 4. Action Queue Surface

Produces a deterministic prioritized queue for planners.

Script:

scripts/list_portfolio_actions.py

Features:

- deterministic sorting  
- repo filtering  
- JSON output for planners  
- optional effectiveness adjustments  

Default priority ordering:

priority  
action_type  
action_id  
repo_id  

With ledger:

adjusted_priority  
priority  
action_type  
action_id  
repo_id  

---

# 5. Action Effectiveness Ledger

Evaluates outcomes of executed actions and adjusts future priorities.

Core module:

src/mcp_governance_orchestrator/action_effectiveness.py

Builder:

scripts/build_action_effectiveness_ledger.py

Produces:

action_effectiveness_ledger.json

Metrics:

success_rate  
avg_risk_delta  
avg_health_delta  
effectiveness_score  
recommended_priority_adjustment  
classification  

---

# 6. Adaptive Planner

Selects tasks based on the action queue.

Planner script:

scripts/claude_dynamic_planner_loop.py

Capabilities:

- consume portfolio_state.json  
- consume effectiveness ledger  
- select top action(s)  
- map action → Tier-3 task  
- execute via run_portfolio_task.py  
- fallback to deterministic tasks if queue empty  

---

# Full Adaptive Loop

Tier-3 execution  
→ artifact bridge  
→ portfolio_state.json  
→ prioritized actions  
→ effectiveness ledger  
→ adjusted priorities  
→ adaptive planner  
→ next execution  

---

# Determinism Guarantees

The system enforces:

- deterministic ordering of actions  
- explicit schema contracts  
- regression tests for all layers  
- fail-closed behavior on malformed inputs  

Current regression coverage:

335 tests passing

---

# Next Evolution (v0.11)

Planned improvement:

Automatic evaluation record generation.

execution  
→ before_state  
→ run action  
→ after_state  
→ evaluation record  
→ effectiveness ledger update  

This will complete a fully autonomous optimization loop.
