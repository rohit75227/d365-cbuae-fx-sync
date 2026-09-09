#!/usr/bin/env python3
"""
Build every FY2019 P1 - FY2026 P9 trial balance period from two monthly-grain
Databricks results (BS movement including CLG, PL movement excluding CLG),
each fetched paginated via the ROW_NUMBER() pattern (12,288-row cap) and
saved to files by the claude-databricks-connector tool. Far more efficient
than running sql/consolidated_trial_balance.sql once per period (93 full
table scans) -- this computes the same numbers from 6 paginated queries by
forward-filling (BS, cumulative since inception) or year-resetting (P&L,
resets every January) the monthly deltas in Python.

Usage:
  python3 scripts/backfill_all_periods.py \
    --bs page1.txt page2.txt page3.txt \
    --pl page1.txt page2.txt page3.txt \
    --out-dir /tmp/backfill

Writes one <out-dir>/report_<FY>-<PP>.json per period plus a summary.json
listing every period key generated, ready for build_db_writes.py.
"""
import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ENTITIES_PATH = SCRIPT_DIR / "entities.json"

EARLIEST_YM = "2019-01"
LATEST_YM = "2026-09"


def load_entities():
    with open(ENTITIES_PATH) as f:
        return json.load(f)["entities"]


def cell_value(cell):
    if "null_value" in cell:
        return None
    return cell.get("string_value")


def load_pages(paths):
    """Parse and concatenate paginated connector results, validating rn continuity."""
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
        for row in raw["result"]["data_array"]:
            all_rows.append([cell_value(v) for v in row["values"]])

    idx = {name: i for i, name in enumerate(columns)}
    rns = sorted(int(r[idx["rn"]]) for r in all_rows)
    expected = list(range(1, len(rns) + 1))
    if rns != expected:
        gaps = sorted(set(expected) - set(rns))
        dupes = [r for r in set(rns) if rns.count(r) > 1]
        raise SystemExit(f"Pagination integrity check failed -- gaps: {gaps[:10]}, dupes: {dupes[:10]}")

    return idx, all_rows


def month_range(start_ym, end_ym):
    y, m = (int(x) for x in start_ym.split("-"))
    ey, em = (int(x) for x in end_ym.split("-"))
    out = []
    while (y, m) <= (ey, em):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


def build_series(idx, rows, reset_yearly):
    """Returns {(entity, account): {ym: (cum_acc, cum_rep)}} forward-filled
    across every month in range, resetting to 0 each January if reset_yearly."""
    deltas = {}  # (entity, account) -> {ym: (acc, rep)}
    names = {}   # account -> name
    for r in rows:
        entity = r[idx["entity_code"]]
        account = r[idx["mainaccountid"]]
        ym = r[idx["ym"]]
        acc = float(r[idx["acc_amt"]] or 0)
        rep = float(r[idx["rep_amt"]] or 0)
        names[account] = r[idx["mainaccountname"]]
        deltas.setdefault((entity, account), {})[ym] = (acc, rep)

    months = month_range(EARLIEST_YM, LATEST_YM)
    series = {}
    for key, ym_deltas in deltas.items():
        cum_acc = 0.0
        cum_rep = 0.0
        per_month = {}
        last_year = None
        for ym in months:
            year = ym[:4]
            if reset_yearly and year != last_year:
                cum_acc = 0.0
                cum_rep = 0.0
                last_year = year
            d_acc, d_rep = ym_deltas.get(ym, (0.0, 0.0))
            cum_acc += d_acc
            cum_rep += d_rep
            per_month[ym] = (cum_acc, cum_rep)
        series[key] = per_month
    return series, names


def period_key(fy, period):
    return f"{fy}-{period:02d}"


def all_periods():
    out = []
    for ym in month_range(EARLIEST_YM, LATEST_YM):
        y, m = ym.split("-")
        out.append((int(y), int(m), ym))
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bs", nargs="+", required=True)
    parser.add_argument("--pl", nargs="+", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    entities = load_entities()
    entity_by_code = {e["code"]: e for e in entities}

    bs_idx, bs_rows = load_pages(args.bs)
    pl_idx, pl_rows = load_pages(args.pl)

    bs_series, bs_names = build_series(bs_idx, bs_rows, reset_yearly=False)
    pl_series, pl_names = build_series(pl_idx, pl_rows, reset_yearly=True)
    names = {**bs_names, **pl_names}

    # Earliest period each (entity, account) ever had real movement -- used
    # below to decide when a row should first appear, never to hide it
    # again afterward (see the "no CLG exclusion" -- an account that nets
    # to exactly zero in some later period, e.g. a year-end intercompany
    # settlement, must still show as 0.00 that period rather than silently
    # disappear and reappear).
    first_ym = {}
    for r in bs_rows:
        key = (r[bs_idx["entity_code"]], r[bs_idx["mainaccountid"]])
        ym = r[bs_idx["ym"]]
        if key not in first_ym or ym < first_ym[key]:
            first_ym[key] = ym
    for r in pl_rows:
        key = (r[pl_idx["entity_code"]], r[pl_idx["mainaccountid"]])
        ym = r[pl_idx["ym"]]
        if key not in first_ym or ym < first_ym[key]:
            first_ym[key] = ym

    generated_keys = []
    for fy, period, ym in all_periods():
        accounts = {}
        control_totals = {code: {"accounting": 0.0, "reporting": 0.0} for code in entity_by_code}

        for (entity, account), per_month in list(bs_series.items()) + list(pl_series.items()):
            if entity not in entity_by_code:
                continue
            if ym < first_ym[(entity, account)]:
                continue  # account genuinely didn't exist yet as of this period
            cum_acc, cum_rep = per_month[ym]
            reporting_amt = cum_rep
            if entity_by_code[entity].get("reportingCurrencyFallback"):
                reporting_amt = cum_acc
            acc = accounts.setdefault(account, {"mainAccountId": account, "mainAccountName": names.get(account, ""), "byEntity": {}})
            acc["byEntity"][entity] = {"accounting": cum_acc, "reporting": reporting_amt}
            control_totals[entity]["accounting"] += cum_acc
            control_totals[entity]["reporting"] += reporting_amt

        warnings = []
        for code, totals in control_totals.items():
            if abs(totals["accounting"]) > 0.01:
                warnings.append(f"{code}: accountingcurrencyamount does not net to zero ({totals['accounting']:.2f})")

        report = {
            "fiscalYear": fy,
            "period": period,
            "generatedAt": "2026-09-03T19:00:00Z",
            "accounts": sorted(accounts.values(), key=lambda a: a["mainAccountId"]),
            "entities": entities,
            "controlTotals": control_totals,
            "warnings": warnings,
        }
        key = period_key(fy, period)
        with open(out_dir / f"report_{key}.json", "w") as f:
            json.dump(report, f)
        generated_keys.append({"fiscalYear": fy, "period": period, "key": key})

    with open(out_dir / "summary.json", "w") as f:
        json.dump({"periods": generated_keys}, f, indent=2)

    print(f"Generated {len(generated_keys)} periods in {out_dir}", file=sys.stderr)


if __name__ == "__main__":
    main()
