# Session Handoff — MCP Governance Orchestrator
**Date:** 2026-03-09
**Branch:** `claude-exp/sandbox-01`
**Tag:** `v0.44.0-alpha`
**Planner version:** 0.36
**Report version:** 0.43

---

## Roles

| Role | Person |
|------|--------|
| System architect | Curtis |
| Experiment design / analysis | ChatGPT |
| Local coding agent | Claude |

---

## 1. Current Repo State

**Core source files:**
- `scripts/claude_dynamic_planner_loop.py` — planner v0.36
- `scripts/generate_experiment_report.py` — report v0.43
- `scripts/run_experiment.sh` — single-command experiment entrypoint
- `agent_tasks/registry.py` — TASK_REGISTRY
- `experiments/portfolio_state_degraded_v2.json` — 5 actions including `recover_failed_workflow`
- `experiments/action_effectiveness_ledger_synthetic_v2.json` — synthetic ledger

**Instrumentation fields live in `selection_detail` of every envelope:**
- `ranked_action_window` — ordered action_type strings from the exploration window
- `active_action_to_task_mapping` — the mapping actually used (default or overridden)
- `action_task_collapse_count` — number of collisions in the window
- `task_diversity_ratio` — unique_tasks / (unique_tasks + collapse), per-run averaged
- `collision_ratio` — total collapse / total window size across all runs (v0.42)
- `task_entropy` — Shannon entropy over selected task distribution (v0.43)
- `action_entropy` — Shannon entropy over ranked window action distribution (v0.43)

**Experiment infrastructure:**
- `mapping_override` in experiment config overrides `ACTION_TO_TASK` for a single run
- CLI: `--mapping-override-json` (JSON string)
- Helper: `resolve_action_to_task_mapping(default, override)` in planner

**Modified file in working tree:**
- `tier3_portfolio_report.csv` — has uncommitted changes (non-blocking)

---

## 2. What Was Implemented This Session

1. **Planner research instrumentation** — `mapping_override`, `collision_ratio`, entropy metrics (`task_entropy`, `action_entropy`) added to planner v0.36 and report v0.43
2. **Experiment config-driven regime control** — `mapping_override` key in JSON config enables regime switching without code changes
3. **Window-size diversity sweep** — configs for topk1–5 across 3 collision regimes (15 configs, 15 result files)
4. **Policy × collision 3×3 matrix** — 9 cells: policies {neutral, insights, fr_focused} × regimes {high, balanced, low}; 3 runs each (27 envelope files, 9 result files)
5. **failure_recovery_focused policy** — added as third policy row to complete the 3×3 matrix

---

## 3. Experiments Run

| Experiment series | Configs | Runs |
|---|---|---|
| Baseline planner (degraded_v2 + ledger_v2) | 5 | ~10 |
| Third-task expansion / diversity | 4 | 8 |
| Mapping-density regime (topk3, offset 0+1) | 6 | 18 |
| Window-size diversity sweep (topk1–5 × 3 regimes) | 15 | 15 |
| Policy × collision 3×3 matrix | 9 | 27 |

All results are deterministic (3 identical runs per cell confirmed).

---

## 4. Key Empirical Findings

### Window-size sweep (by regime)

| Regime | topk | selected | task_entropy | action_entropy | collision_ratio |
|--------|------|----------|-------------|----------------|-----------------|
| low_collision | 1–5 | 1–5 | grows 0→2.32 | grows 0→2.32 | 0.0 always |
| balanced | 1–3 | 1–3 | grows 0→1.58 | grows 0→1.58 | 0.0 |
| balanced | 4–5 | 3 | **saturates 1.58** | keeps growing | 0.25–0.40 |
| high_collision | 1–2 | 1–2 | grows 0→1.0 | grows 0→1.0 | 0.0 |
| high_collision | 3–5 | 2–3 | **saturates 1.0–1.58** | keeps growing | 0.25–0.40 |

**Critical pattern:** `action_entropy` keeps growing with window size across all regimes (it tracks the window). `task_entropy` diverges from `action_entropy` the moment collisions appear. The divergence point is regime-dependent.

### Policy × collision 3×3 matrix

| policy | collision_regime | task_entropy | collision_ratio | unique_tasks |
|--------|-----------------|-------------|-----------------|--------------|
| neutral | high | **1.0** | 0.333 | 2 |
| neutral | balanced | 1.584 | 0.0 | 3 |
| neutral | low | 1.584 | 0.0 | 3 |
| insights | **high** | **1.584** | **0.0** | **3** |
| insights | balanced | 1.0 | 0.333 | 2 |
| insights | low | 1.584 | 0.0 | 3 |
| fr_focused | high | 1.0 | 0.333 | 2 |
| fr_focused | balanced | 1.0 | 0.333 | 2 |
| fr_focused | low | 1.584 | 0.0 | 3 |

**Standout cell:** `insights + high` achieves zero collision despite high-collision mapping. Why: the insights policy changes the ranked window to `[refresh_repo_health, analyze_repo_insights, recover_failed_workflow]` — three actions that map to three distinct tasks. The two high-collision actions (`regenerate_missing_artifact`, `rerun_failed_task`) are pushed out of the top-3. The mapping's inherent collision density is never realized.

---

## 5. Mechanistic Interpretation

The causal chain governing task diversity is:

```
policy
  → ranked_action_window (which actions enter top-k)
    → action→task clustering within that window (realized collisions)
      → action_task_collapse_count / collision_ratio
        → task_entropy (realized task diversity)
```

**Key principles confirmed:**

1. **action_entropy is window-driven and stable** for a fixed top-k window. It measures how many distinct actions appeared, not how useful they are.

2. **task_entropy is collision-regime-gated.** It can never exceed the maximum entropy achievable given the unique tasks reachable from the window. Collision saturates it early.

3. **Collision effects are window-composition-dependent, not simply mapping-density-dependent.** A "high-collision" mapping only produces collisions if the high-collision actions actually appear together in the window. Policy can suppress or expose that collision.

4. **Low-collision mappings produce linear diversity growth with top_k.** Every new action in the window maps to a new task. task_entropy ≡ action_entropy.

5. **Higher-collision mappings saturate task_entropy earlier.** task_entropy diverges from action_entropy at the topk where the first collision enters the window.

6. **Policy shapes diversity indirectly, by controlling window composition.** Policy does not directly set diversity; it selects which actions compete for the top-k slots, which determines whether collision-prone actions co-occupy the window.

---

## 6. What Not To Redo

- Do not re-run the window-size sweep (topk1–5 × 3 regimes) — complete, deterministic, results on disk.
- Do not re-run the 3×3 policy × collision matrix — all 9 cells run 3x each, results on disk.
- Do not add more collision regimes or policy variants without a concrete design question. The causal model is now clear.
- Do not modify PLANNER_VERSION or REPORT_VERSION without an explicit change ticket. Both are stable.
- Do not touch `instrumented_*.json` static fixtures — they are regression baselines.
- Do not re-implement entropy metrics — `_entropy()` in report v0.43 is correct and deterministic.

---

## 7. Best Next Step

**Consolidate findings into a persistent experiment summary artifact.**

The experiments are done. The raw data is on disk. What is missing is a durable, human-readable synthesis that can anchor future design decisions. Specifically:

1. **Write `experiments/EXPERIMENT_SUMMARY.md`** — a permanent artifact containing:
   - The 3×3 matrix table
   - The window-size sweep table
   - The causal chain diagram
   - The key design-relevant conclusions (what levers exist, what their effects are)

2. **Generate and commit formal reports** — run `generate_experiment_report.py` on the key result files and commit the `.md` outputs alongside the raw results.

3. **Archive the experiment branch** — once summary is committed, open a PR to merge the experiment branch into `main` (scope: experiment data + instrumentation only, no planner behavior changes).

This is a consolidation task, not an implementation task. No new code is needed.

---

## 8. End-of-Run Report

**Objective:** Produce a consolidated session handoff for the next session.

**Files changed:** None (read-only analysis run).

**Commands run:**
- `git log --oneline -20`
- `python3 scripts/generate_experiment_report.py` (on temp files, not committed)
- Various `python3 -c` analysis scripts (read-only)

**Tests run:** None (analysis session only).

**Contract impact:** None. No source files modified.

**Risks / uncertainties:**
- The `tier3_portfolio_report.csv` file has uncommitted changes — confirm whether these are intentional before next commit.
- The `instrumented_*.json` static fixtures do not yet carry entropy/collision_ratio fields (they were generated before v0.42). They will fail entropy regression assertions if those are ever added. Pre-existing gap, not introduced this session.

**Recommended next step:** See section 7 above.
