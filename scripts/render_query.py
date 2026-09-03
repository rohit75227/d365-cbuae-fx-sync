#!/usr/bin/env python3
"""
Render sql/consolidated_trial_balance.sql for a given as-of period, ready to
paste into the claude-databricks-connector's execute_sql_read_only tool.

The connector takes a raw SQL string with no parameter binding, so this
substitutes the {{PERIOD_END_EXCLUSIVE}} / {{FY_START}} tokens with literal
TIMESTAMP values rather than relying on query parameters.

Usage:
  python3 scripts/render_query.py --fiscal-year 2026 --period 8
  # period 8 = August; period end is the first instant of the *next* month,
  # so "period 8" means "through the end of August" and works whether or not
  # August has actually closed yet.
"""
import argparse
from pathlib import Path

SQL_PATH = Path(__file__).resolve().parent.parent / "sql" / "consolidated_trial_balance.sql"


def period_end_exclusive(fiscal_year: int, period: int) -> str:
    if period == 12:
        return f"{fiscal_year + 1}-01-01"
    return f"{fiscal_year}-{period + 1:02d}-01"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fiscal-year", type=int, required=True)
    parser.add_argument("--period", type=int, required=True, choices=range(1, 13))
    args = parser.parse_args()

    fy_start = f"{args.fiscal_year}-01-01"
    period_end = period_end_exclusive(args.fiscal_year, args.period)

    sql = SQL_PATH.read_text()
    sql = sql.replace("{{PERIOD_END_EXCLUSIVE}}", f"TIMESTAMP'{period_end} 00:00:00'")
    sql = sql.replace("{{FY_START}}", f"TIMESTAMP'{fy_start} 00:00:00'")
    print(sql)


if __name__ == "__main__":
    main()
