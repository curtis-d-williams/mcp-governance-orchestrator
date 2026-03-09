# MCP Governance Orchestrator — Experiment Summary
**Date:** 2026-03-09
**Branch:** `claude-exp/sandbox-01`
**Planner version:** 0.36 | **Report version:** 0.43

This document is a permanent synthesis of the planner research experiments run on this branch.
It is not regenerated; the raw data lives in `experiments/*_results.json`.

---

## 1. What Was Measured

Every planner run produces a `selection_detail` envelope with:

| Field | Description |
|-------|-------------|
| `ranked_action_window` | Top-k actions ordered by score before dedup |
| `active_action_to_task_mapping` | ACTION_TO_TASK mapping actually used |
| `action_task_collapse_count` | # actions in window that mapped to an already-seen task |
| `task_diversity_ratio` | unique_tasks / (unique_tasks + collapse), per-run average |
| `collision_ratio` | total collapse / total window size across all runs |
| `task_entropy` | Shannon entropy (bits) over task distribution in window |
| `action_entropy` | Shannon entropy (bits) over action distribution in window |

`task_entropy` measures realized task diversity.
`action_entropy` measures action variety in the window — independent of task mapping.

---

## 2. Collision Regimes

Three mapping regimes were defined via `mapping_override` in experiment configs:

| Regime | Mapping | Max unique tasks at topk=3 |
|--------|---------|---------------------------|
| **high_collision** | regen→dashboard, rerun→dashboard, refresh→dashboard, analyze→insights, recover→failure_recovery | 2 (3 actions collapse to 1 task) |
| **balanced** | regen→dashboard, rerun→failure_recovery, refresh→insights, analyze→insights, recover→failure_recovery | 3 (pairs can collide: refresh/analyze→insights, rerun/recover→failure_recovery) |
| **low_collision** | regen→dashboard, rerun→failure_recovery, refresh→insights, analyze→determinism, recover→audit | 3+ (all 5 actions map to distinct tasks) |

---

## 3. Window-Size Diversity Sweep (topk 1–5 × 3 regimes)

Each cell = 1 run (deterministic, confirmed with 3-run checks at topk=5).

| Regime | topk | unique_tasks | task_entropy | action_entropy | collision_ratio |
|--------|------|-------------|-------------|----------------|-----------------|
| low_collision | 1 | 1.0 | 0.000 | 0.000 | 0.000 |
| low_collision | 2 | 2.0 | 1.000 | 1.000 | 0.000 |
| low_collision | 3 | 3.0 | 1.585 | 1.585 | 0.000 |
| low_collision | 4 | 4.0 | 2.000 | 2.000 | 0.000 |
| low_collision | 5 | 5.0 | 2.322 | 2.322 | 0.000 |
| balanced | 1 | 1.0 | 0.000 | 0.000 | 0.000 |
| balanced | 2 | 2.0 | 1.000 | 1.000 | 0.000 |
| balanced | 3 | 3.0 | 1.585 | 1.585 | 0.000 |
| **balanced** | **4** | **3.0** | **1.500** | **2.000** | **0.250** |
| **balanced** | **5** | **3.0** | **1.522** | **2.322** | **0.400** |
| high_collision | 1 | 1.0 | 0.000 | 0.000 | 0.000 |
| high_collision | 2 | 2.0 | 1.000 | 1.000 | 0.000 |
| **high_collision** | **3** | **2.0** | **0.918** | **1.585** | **0.333** |
| high_collision | 4 | 3.0 | 1.500 | 2.000 | 0.250 |
| **high_collision** | **5** | **3.0** | **1.371** | **2.322** | **0.400** |

**Collision onset point** (where task_entropy diverges from action_entropy):
- low_collision: never (no collisions exist in this mapping)
- balanced: topk=4 (4th action enters a pair that shares a task)
- high_collision: topk=3 (3rd action completes the dashboard-triple)

---

## 4. Policy × Collision 3×3 Matrix

Each cell = 3 identical runs (full determinism confirmed).
All cells used topk=3.

| Policy | Collision regime | Ranked window | unique_tasks | task_entropy | action_entropy | collision_ratio |
|--------|-----------------|---------------|-------------|-------------|----------------|-----------------|
| neutral | high | regen, recover, refresh | 2.0 | 0.918 | 1.585 | 0.333 |
| neutral | balanced | regen, recover, refresh | 3.0 | 1.585 | 1.585 | 0.000 |
| neutral | low | regen, recover, refresh | 3.0 | 1.585 | 1.585 | 0.000 |
| insights | **high** | refresh, analyze, recover | **3.0** | **1.585** | **1.585** | **0.000** |
| insights | balanced | refresh, analyze, recover | 2.0 | 0.918 | 1.585 | 0.333 |
| insights | low | refresh, analyze, recover | 3.0 | 1.585 | 1.585 | 0.000 |
| fr_focused | high | recover, rerun, refresh | 2.0 | 0.918 | 1.585 | 0.333 |
| fr_focused | balanced | recover, rerun, refresh | 2.0 | 0.918 | 1.585 | 0.333 |
| fr_focused | low | recover, rerun, refresh | 3.0 | 1.585 | 1.585 | 0.000 |

### Policy definitions

| Policy | `artifact_completeness` weight | `recent_failures` weight | `stale_runs` weight |
|--------|-------------------------------|--------------------------|---------------------|
| neutral | (default) | (default) | (default) |
| insights_first | -1.0 | -1.0 | 0.0 |
| failure_recovery_focused | -5.0 | +5.0 | 0.0 |

### Standout cell: `insights + high_collision`

The insights policy elevates `refresh_repo_health` and `analyze_repo_insights` (by penalizing artifact-complete and non-failing actions) and happens to surface `[refresh, analyze, recover]` as the top-3 window. Under the high-collision mapping:
- `refresh_repo_health` → `build_portfolio_dashboard`
- `analyze_repo_insights` → `repo_insights_example`
- `recover_failed_workflow` → `failure_recovery_example`

All three map to distinct tasks → zero collision. The high-collision mapping's density was never realized, because the three high-collision actions (`regen`, `rerun`, `refresh`) were not co-present in the window.

This is not a special property of the insights policy in general — under the balanced regime, `insights` produces a different collision because `analyze` and `refresh` both map to `repo_insights_example` in that mapping.

---

## 5. Causal Chain

```
policy weights
  → action score adjustments
    → ranked_action_window composition (which top-k actions enter)
      → intersection with mapping collision structure
        → action_task_collapse_count  (realized collisions)
          → collision_ratio           (aggregate over runs)
            → task_entropy            (realized task diversity)
```

`action_entropy` branches off after `ranked_action_window` — it measures the window's action variety independently of mapping.

---

## 6. Key Design-Relevant Conclusions

### 6.1 action_entropy and task_entropy diverge at the collision onset point
Below the onset topk, `task_entropy == action_entropy` (every new action brings a new task).
Above it, `action_entropy` grows but `task_entropy` saturates or grows more slowly.
The divergence magnitude is a direct measure of mapping inefficiency.

### 6.2 Collision effects are window-composition-dependent
A "high-collision" mapping only produces collisions when the high-collision actions
co-occupy the window. Whether they do is controlled by policy. This means:
- Collision regime alone does not determine task diversity.
- The same mapping can yield zero or full-collision depending on which actions the policy promotes.

### 6.3 Policy shapes diversity indirectly
Policy does not directly set task diversity — it selects window composition, which determines
whether collision-prone pairs enter together. To reason about diversity, trace the full chain:
policy → window → collision structure → entropy.

### 6.4 Low-collision mappings are linear and predictable
In a low-collision mapping, every added topk slot contributes one new task.
`task_entropy ≡ action_entropy` throughout. This is the ideal case for diversity-aware scheduling.

### 6.5 High-collision mappings produce non-monotonic diversity
In a high-collision mapping, diversity can *decrease* as topk grows past the onset point
(e.g., high_collision topk=3 has lower task_entropy than topk=2 in the neutral-policy case).
This is because topk=3 adds a third action that shares a task with an existing one.

### 6.6 The planner's dedup step is the diversity enforcement mechanism
The dedup step in `select_actions()` already eliminates duplicate task assignments.
`action_task_collapse_count` counts how many actions were dropped by this step.
Improving diversity requires changing what enters the window, not the dedup logic.

---

## 7. What Was Not Explored

- Ledger-weight sensitivity (how ledger scores interact with policy weights)
- Multi-run averaging effects when exploration_offset > 0
- Behavior with more than 5 portfolio actions
- Any actual task execution outcomes (all experiments use mock task runs)

These are out of scope for this research phase. The causal model above is sufficient for
guiding planner and policy design decisions in the next implementation phase.

---

## 8. Raw Data Index

| Series | Config glob | Result glob | Runs/cell |
|--------|-------------|-------------|-----------|
| Window-size sweep | `mapping_regime_*_topk*_config.json` | `mapping_regime_*_topk*_results.json` | 1 (3 for topk5) |
| Policy × collision | `policy_x_collision_*_config.json` | `policy_x_collision_*_results.json` | 3 |
| Mapping-density offset sweep | `mapping_regime_*_offset*_config.json` | `mapping_regime_*_offset*_results.json` | 3 |
| Baseline (neutral, insights, fr) | `baseline_*_config.json` | `baseline_*_results.json` | 1–3 |

Static regression fixtures (do not regenerate):
- `experiments/instrumented_neutral_offset0.json`
- `experiments/instrumented_neutral_offset1.json`
- `experiments/instrumented_insights_offset0.json`
