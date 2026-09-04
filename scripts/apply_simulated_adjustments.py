#!/usr/bin/env python3
"""
Apply an explicitly-labeled, NOT-YET-POSTED pro-forma adjustment to a report
JSON (the output of transform_connector_result.py), for cases where finance
wants to see the trial balance "as if" a known-pending D365 entry had
already been posted.

The adjustment amount is ALWAYS computed dynamically from this period's own
controlTotals -- never pass a fixed dollar figure copied from another
period. An unclosed-year gap like HBCB's or HBUK's grows over time (more
fiscal years go unclosed), so a figure that exactly zeroes one period
massively overcorrects a different one. Caught 2026-09-04: a hardcoded
adjustment sized for FY2026 turned Dec 2025's real +2.39M gap into a
-275.7M one when applied there too.

This never touches the SQL query or Databricks -- it's a post-processing
step on top of real GL data, and every adjustment it applies is recorded in
the output's `simulatedAdjustments` list so the report can render a clear,
separate notice (never silently blended into "actual" figures). Use this
only when a report viewer has explicitly asked to see a specific pending
transfer simulated -- never invent an adjustment to make a control total
look clean, and never simulate an entity that already nets to ~0.00 for
this period (nothing pending here, don't touch it).

Usage:
  python3 scripts/apply_simulated_adjustments.py report.json \
    --entity HBCB --account 3141001 --account-name "Retained Earnings - Accumulated" \
    --reason "Simulated year-end close (not yet posted in D365) -- transfers HBCB's unclosed prior-year P&L into Retained Earnings" \
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
    parser.add_argument("--reason", required=True)
    args = parser.parse_args()

    with open(args.report_file) as f:
        report = json.load(f)

    totals = report.get("controlTotals", {}).get(args.entity, {"accounting": 0.0, "reporting": 0.0})
    if abs(totals["accounting"]) <= 0.01 and abs(totals["reporting"]) <= 0.01:
        # Nothing pending for this entity this period -- pass the report through unchanged.
        json.dump(report, sys.stdout)
        return

    accounting_delta = -totals["accounting"]
    reporting_delta = -totals["reporting"]

    account = next((a for a in report["accounts"] if a["mainAccountId"] == args.account), None)
    if account is None:
        account = {"mainAccountId": args.account, "mainAccountName": args.account_name, "byEntity": {}}
        report["accounts"].append(account)
        report["accounts"].sort(key=lambda a: a["mainAccountId"])

    cell = account["byEntity"].setdefault(args.entity, {"accounting": 0.0, "reporting": 0.0})
    cell["accounting"] = (cell.get("accounting") or 0.0) + accounting_delta
    cell["reporting"] = (cell.get("reporting") or 0.0) + reporting_delta

    report.setdefault("simulatedAdjustments", []).append({
        "entity": args.entity,
        "mainAccountId": args.account,
        "mainAccountName": args.account_name,
        "accountingDelta": accounting_delta,
        "reportingDelta": reporting_delta,
        "reason": args.reason,
    })

    report.setdefault("controlTotals", {})[args.entity] = {"accounting": 0.0, "reporting": 0.0}

    warnings = report.get("warnings", [])
    warnings = [w for w in warnings if not w.startswith(f"{args.entity}:")]
    warnings.append(
        f"{args.entity}: includes a SIMULATED adjustment of {accounting_delta:,.2f} to "
        f"{args.account} \"{args.account_name}\" -- {args.reason}"
    )
    report["warnings"] = warnings

    json.dump(report, sys.stdout)


if __name__ == "__main__":
    main()
