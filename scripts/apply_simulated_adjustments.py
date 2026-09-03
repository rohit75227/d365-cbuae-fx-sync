#!/usr/bin/env python3
"""
Apply explicitly-labeled, NOT-YET-POSTED pro-forma adjustments to a report
JSON (the output of transform_connector_result.py), for cases where finance
wants to see the trial balance "as if" a known-pending D365 entry had
already been posted.

This never touches the SQL query or Databricks -- it's a post-processing
step on top of real GL data, and every adjustment it applies is recorded in
the output's `simulatedAdjustments` list so the report can render a clear,
separate notice (never silently blended into "actual" figures). Use this
only when a report viewer has explicitly asked to see a specific pending
transfer simulated -- never invent an adjustment to make a control total
look clean.

Usage:
  python3 scripts/apply_simulated_adjustments.py report.json \
    --entity HBCB --account 3141001 --account-name "Retained Earnings - Accumulated" \
    --accounting-delta -278118823.426 --reporting-delta -278118823.426 \
    --reason "Simulated FY2025 year-end close (not yet posted in D365 as of 2026-09-03) -- transfers HBCB's unclosed FY2024/2025 P&L into Retained Earnings" \
    > report_adjusted.json
"""
import argparse
import json
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("report_file")
    parser.add_argument("--entity", required=True)
    parser.add_argument("--account", required=True)
    parser.add_argument("--account-name", required=True)
    parser.add_argument("--accounting-delta", type=float, required=True)
    parser.add_argument("--reporting-delta", type=float, required=True)
    parser.add_argument("--reason", required=True)
    args = parser.parse_args()

    with open(args.report_file) as f:
        report = json.load(f)

    account = next((a for a in report["accounts"] if a["mainAccountId"] == args.account), None)
    if account is None:
        account = {"mainAccountId": args.account, "mainAccountName": args.account_name, "byEntity": {}}
        report["accounts"].append(account)
        report["accounts"].sort(key=lambda a: a["mainAccountId"])

    cell = account["byEntity"].setdefault(args.entity, {"accounting": 0.0, "reporting": 0.0})
    cell["accounting"] = (cell.get("accounting") or 0.0) + args.accounting_delta
    cell["reporting"] = (cell.get("reporting") or 0.0) + args.reporting_delta

    report.setdefault("simulatedAdjustments", []).append({
        "entity": args.entity,
        "mainAccountId": args.account,
        "mainAccountName": args.account_name,
        "accountingDelta": args.accounting_delta,
        "reportingDelta": args.reporting_delta,
        "reason": args.reason,
    })

    # Recompute this entity's control total so the warning reflects reality
    # (adjusted-to-balance, not "still broken") rather than going stale.
    totals = report.setdefault("controlTotals", {}).setdefault(args.entity, {"accounting": 0.0, "reporting": 0.0})
    totals["accounting"] += args.accounting_delta
    totals["reporting"] += args.reporting_delta

    warnings = report.get("warnings", [])
    warnings = [w for w in warnings if not w.startswith(f"{args.entity}:")]
    if abs(totals["accounting"]) > 0.01:
        warnings.append(f"{args.entity}: accountingcurrencyamount does not net to zero ({totals['accounting']:.2f})")
    warnings.append(
        f"{args.entity}: includes a SIMULATED adjustment of {args.accounting_delta:,.2f} to "
        f"{args.account} \"{args.account_name}\" -- {args.reason}"
    )
    report["warnings"] = warnings

    json.dump(report, sys.stdout)


if __name__ == "__main__":
    main()
