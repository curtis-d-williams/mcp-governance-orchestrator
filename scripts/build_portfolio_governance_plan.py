# SPDX-License-Identifier: MIT
"""Thin CLI wrapper for Phase Q portfolio governance planning."""

import argparse

from portfolio_governance_runtime import _write_json, build_plan


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--output-dir", required=True, dest="output_dir")
    parser.add_argument("--max-repos-per-cycle", type=int, default=None)

    args = parser.parse_args()

    plan = build_plan(
        args.manifest,
        args.output_dir,
        max_repos_per_cycle=args.max_repos_per_cycle,
    )
    _write_json(args.output, plan)


if __name__ == "__main__":
    main()
