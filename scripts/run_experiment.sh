#!/usr/bin/env bash
set -euo pipefail

CONFIG_PATH="${1:-experiment_config.json}"

if [[ ! -f "$CONFIG_PATH" ]]; then
  echo "Missing experiment config: $CONFIG_PATH" >&2
  exit 1
fi

python3 scripts/run_planner_experiment.py --config "$CONFIG_PATH"

if [[ -f experiment_results.json ]]; then
  if [[ -f policy_sweep_results.json ]]; then
    python3 scripts/generate_experiment_report.py \
      --experiment-results experiment_results.json \
      --policy-sweep-results policy_sweep_results.json
  else
    python3 scripts/generate_experiment_report.py \
      --experiment-results experiment_results.json
  fi
fi

echo "Experiment run complete."
