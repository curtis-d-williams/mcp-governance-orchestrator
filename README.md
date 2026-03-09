# MCP Governance Orchestrator
Adaptive automation factory for multi-repository governance and analysis.

Current architecture milestone: **v0.10.0-alpha**

This repository implements a deterministic automation system that:

- executes Tier-3 portfolio tasks
- derives portfolio state
- generates prioritized actions
- evaluates action outcomes
- adaptively adjusts task prioritization

The system forms a closed optimization loop.

---

# Architecture

Full architecture reference:

docs/ARCHITECTURE_V0_10.md

High-level loop:

Tier-3 execution  
→ artifact bridge  
→ portfolio_state.json  
→ prioritized action queue  
→ effectiveness ledger  
→ adaptive planner  
→ next execution

---

# Core Scripts

Tier-3 execution

scripts/run_portfolio_task.py

Portfolio state

scripts/build_portfolio_state_from_artifacts.py  
scripts/build_portfolio_state.py

Action queue

scripts/list_portfolio_actions.py

Effectiveness evaluation

scripts/build_action_effectiveness_ledger.py

Adaptive planner

scripts/claude_dynamic_planner_loop.py

---

# Running Tests

Run the full regression suite:

pytest -q

Current coverage:

> ~335 tests passing

---

# Key Artifacts

Tier-3 outputs

tier3_portfolio_report.csv  
tier3_multi_run_aggregate.json  

Control plane

portfolio_state.json  

Adaptive evaluation

action_effectiveness_ledger.json  

---

# Development Status

Current milestone:

v0.10.0-alpha

Adaptive portfolio control plane and effectiveness-driven planner loop implemented.

Next milestone:

v0.11  
automatic evaluation record generation to fully close the optimization loop.

---

## Running Planner Experiments

The repository includes a deterministic experiment pipeline for evaluating planner behavior.

### Run a local experiment

python scripts/run_planner_experiment.py --config experiment_config.json

### Generate a report

python scripts/generate_experiment_report.py

This produces:

experiment_results.json
experiment_report.json
experiment_report.md

### Single-command local run

./scripts/run_experiment.sh

Optional custom config:

./scripts/run_experiment.sh path/to/experiment_config.json

### Policy sweep experiments

Experiments can define multiple governance policies inside the config file.

python scripts/run_planner_experiment.py --config experiment_config.json

The system will generate:

policy_sweep_results.json

### CI experiments

The repository includes a GitHub Actions workflow that runs experiments automatically when:

- a commit is pushed
- a pull request is opened

Artifacts produced by CI include:

experiment_results.json  
policy_sweep_results.json  
experiment_report.json  
experiment_report.md  
planner_run_envelope_*.json
