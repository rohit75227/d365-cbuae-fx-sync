#!/usr/bin/env python3
"""
Build per-period, per-(entity, account) Current Month Dr/Cr movement docs
from the paginated sql/monthly_movement.sql result, for the "Company TB" tab
(Opening Balance -> Current Month Dr -> Current Month Cr -> Closing Balance).

Unlike backfill_all_periods.py this needs NO forward-fill/year-reset --
monthly movement is already the right grain, it's not a cumulative balance.
The report combines it client-side with the already-published tb/<period>
closing balances: Opening = prior period's closing (0 in January for P&L
accounts, since those reset each fiscal year), Closing = this period's
already-published closing, Dr/Cr = this file's numbers for that (entity,
account, period).

Usage:
  python3 scripts/build_monthly_movement.py \
    --pages page_1.json page_2.json ... \
    --validate-against-dir /path/to/report_<period>.json/dir \
    --out-dir /tmp/movement_out

Writes one <out-dir>/movement_<FY>-<PP>.json per period plus summary.json.
"""
import argparse
import json
from pathlib import Path


def cell_value(cell):
    # The connector has used two different per-cell shapes across sessions
    # (both observed live): older data_array/{"string_value": ...} and
    # current data_typed_array/{"str": ...} -- support both rather than
    # assuming whichever one this session happened to see first.
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
    parser.add_argument("--validate-against-dir", help="dir of report_<period>.json from backfill_all_periods.py, for a spot-check")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    idx, rows = load_pages(args.pages)

    # period -> [{mainAccountId, mainAccountName, entity, debitAccounting, creditAccounting, debitReporting, creditReporting}]
    by_period = {}
    names = {}
    for r in rows:
        ym = r[idx["ym"]]
        entity = r[idx["entity_code"]]
        account = r[idx["mainaccountid"]]
        name = r[idx["mainaccountname"]]
        names[account] = name
        rec = {
            "mainAccountId": account,
            "mainAccountName": name,
            "entity": entity,
            "debitAccounting": float(r[idx["debit_acc"]] or 0),
            "creditAccounting": float(r[idx["credit_acc"]] or 0),
            "debitReporting": float(r[idx["debit_rep"]] or 0),
            "creditReporting": float(r[idx["credit_rep"]] or 0),
        }
        by_period.setdefault(ym, []).append(rec)

    periods_written = []
    for ym, records in sorted(by_period.items()):
        y, m = ym.split("-")
        fy, period = int(y), int(m)
        out = {
            "fiscalYear": fy,
            "period": period,
            "movement": records,
        }
        fname = out_dir / f"movement_{fy}-{period:02d}.json"
        with open(fname, "w") as f:
            json.dump(out, f)
        periods_written.append(f"{fy}-{period:02d}")

    with open(out_dir / "summary.json", "w") as f:
        json.dump({"periods": periods_written}, f, indent=2)

    print(f"Wrote {len(periods_written)} movement periods to {out_dir}")

    if args.validate_against_dir:
        validate(by_period, Path(args.validate_against_dir))


def validate(by_period, balances_dir):
    """Spot-check: for several (entity, account, period) combos, opening
    (prior period's stored closing, 0 in Jan for P&L) + Dr - Cr should equal
    this period's stored closing, within rounding."""
    import random

    checked = 0
    failures = []
    periods = sorted(by_period.keys())
    sample_periods = periods[::13]  # spread across history, ~7 samples
    for ym in sample_periods:
        y, m = ym.split("-")
        fy, period = int(y), int(m)
        cur_path = balances_dir / f"report_{fy}-{period:02d}.json"
        if not cur_path.exists():
            continue
        with open(cur_path) as f:
            cur = json.load(f)
        prev_period = period - 1
        prev_fy = fy
        if prev_period == 0:
            prev_period = 12
            prev_fy = fy - 1
        prev_path = balances_dir / f"report_{prev_fy}-{prev_period:02d}.json"
        prev = None
        if prev_path.exists():
            with open(prev_path) as f:
                prev = json.load(f)

        cur_bal = {(a["mainAccountId"], e): v["accounting"]
                   for a in cur["accounts"]
                   for e, v in a["byEntity"].items()}
        prev_bal = {}
        if prev:
            prev_bal = {(a["mainAccountId"], e): v["accounting"]
                        for a in prev["accounts"]
                        for e, v in a["byEntity"].items()}

        is_pl = None
        movement_rows = by_period.get(ym, [])
        sample = movement_rows[:200]
        for rec in sample:
            key = (rec["mainAccountId"], rec["entity"])
            if key not in cur_bal:
                continue
            closing = cur_bal[key]
            is_pl_acc = int(rec["mainAccountId"]) >= 4000000
            if is_pl_acc and period == 1:
                opening = 0.0
            else:
                opening = prev_bal.get(key, 0.0)
            expected_closing = opening + rec["debitAccounting"] - rec["creditAccounting"]
            diff = abs(expected_closing - closing)
            checked += 1
            if diff > 1.0:
                failures.append((ym, key, opening, rec["debitAccounting"], rec["creditAccounting"], expected_closing, closing, diff))

    print(f"Validated {checked} (entity, account, period) combos across {len(sample_periods)} sample periods")
    if failures:
        print(f"{len(failures)} FAILURES (diff > 1.0):")
        for f in failures[:20]:
            print(" ", f)
    else:
        print("All sampled combos: Opening + Dr - Cr == stored Closing (within rounding). OK.")


if __name__ == "__main__":
    main()
