#!/usr/bin/env python3
"""
Usage:
  python run.py              # process last 1 day
  python run.py --days 3     # process last 3 days
"""
import argparse
from orchestrator import Orchestrator
from tools.cost_tracker import BudgetExceeded, BUDGET_USD


def main():
    parser = argparse.ArgumentParser(description="Daily newsletter & podcast summarizer")
    parser.add_argument("--days", type=int, default=1, help="Days back to fetch (default: 1)")
    parser.add_argument("--budget", type=float, default=BUDGET_USD, help=f"Cost limit in USD (default: ${BUDGET_USD})")
    args = parser.parse_args()

    import tools.cost_tracker as ct
    ct.BUDGET_USD = args.budget

    print(f"Budget: ${args.budget:.2f}")
    try:
        Orchestrator().run(days_back=args.days)
    except BudgetExceeded as e:
        print(f"\n{e}")


if __name__ == "__main__":
    main()
