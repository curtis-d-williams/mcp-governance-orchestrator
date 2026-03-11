# SPDX-License-Identifier: MIT
"""Thin CLI wrapper for portfolio governance batch execution."""

import argparse

from portfolio_governance_runtime import (
    aggregate,
    run_portfolio_governance_batch,
    run_repo_cycle,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--task", action="append", required=True)

    args = parser.parse_args()
    return run_portfolio_governance_batch(args)


if __name__ == "__main__":
    raise SystemExit(main())
