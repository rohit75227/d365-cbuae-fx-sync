#!/usr/bin/env python3
"""
Build the "By Currency" tab's per-period, per-(entity, account, currency)
Current Month Dr/Cr movement docs, from the SAME already-fetched
sql/monthly_movement_by_currency.sql pages used by build_currency_series.py
for the closing-balance reconstruction -- no new Databricks query needed,
this is just a different aggregation of the same rows.

Mirrors scripts/build_monthly_movement.py, keyed by (entity, account,
currency, ym) instead of (entity, account, ym).

Usage:
  python3 scripts/build_currency_movement.py --pages page_1.json ... --out-dir /tmp/currency_movement_out
"""
import argparse
import json
from pathlib import Path


def cell_value(cell):
    # Support both connector cell shapes observed live across sessions:
    # older data_array/{"string_value": ...} and current
    # data_typed_array/{"str": ...}.
    if "null_value" in cell:
        return None
    if "string_value" in cell:
        return cell["string_value"]
    if "str" in cell:
        return cell["str"]
    return None


def load_pages(paths):
    all_rows = []
    columns = None
    for p in paths:
        with open(p) as f:
            raw = json.load(f)
        if raw["manifest"].get("truncated") or raw.get("truncated"):
            raise SystemExit(f"{p}: result was truncated -- page size too large, shrink it")
        cols = [c["name"] for c in raw["manifest"]["schema"]["columns"]]
        if columns is None:
            columns = cols
        elif columns != cols:
            raise SystemExit(f"{p}: column mismatch across pages")
        data_rows = raw["result"].get("data_array")
        if data_rows is None:
            data_rows = raw["result"]["data_typed_array"]
        for row in data_rows:
            all_rows.append([cell_value(v) for v in row["values"]])

    idx = {name: i for i, name in enumerate(columns)}
    rns = sorted(int(r[idx["rn"]]) for r in all_rows)
    expected = list(range(1, len(rns) + 1))
    if rns != expected:
        gaps = sorted(set(expected) - set(rns))
        dupes = [r for r in set(rns) if rns.count(r) > 1]
        raise SystemExit(f"Pagination integrity check failed -- gaps: {gaps[:10]}, dupes: {dupes[:10]}")

    return idx, all_rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pages", nargs="+", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    idx, rows = load_pages(args.pages)

    by_period = {}
    for r in rows:
        ym = r[idx["ym"]]
        rec = {
            "mainAccountId": r[idx["mainaccountid"]],
            "mainAccountName": r[idx["mainaccountname"]],
            "txnCurrency": r[idx["txn_ccy"]],
            "entity": r[idx["entity_code"]],
            "debitAccounting": float(r[idx["debit_acc"]] or 0),
            "creditAccounting": float(r[idx["credit_acc"]] or 0),
            "debitReporting": float(r[idx["debit_rep"]] or 0),
            "creditReporting": float(r[idx["credit_rep"]] or 0),
            "debitTransaction": float(r[idx["debit_txn"]] or 0),
            "creditTransaction": float(r[idx["credit_txn"]] or 0),
        }
        by_period.setdefault(ym, []).append(rec)

    periods_written = []
    for ym, records in sorted(by_period.items()):
        y, m = ym.split("-")
        fy, period = int(y), int(m)
        out = {"fiscalYear": fy, "period": period, "movement": records}
        fname = out_dir / f"movement_{fy}-{period:02d}.json"
        with open(fname, "w") as f:
            json.dump(out, f)
        periods_written.append(f"{fy}-{period:02d}")

    with open(out_dir / "summary.json", "w") as f:
        json.dump({"periods": periods_written}, f, indent=2)

    print(f"Wrote {len(periods_written)} movement-by-currency periods to {out_dir}")


if __name__ == "__main__":
    main()
