#!/usr/bin/env python3
"""
Rebuild the full closing-balance series (same output shape as
backfill_all_periods.py) directly from the monthly Dr/Cr movement pages
(sql/monthly_movement.sql), instead of a separate BS/PL delta fetch.

Why: the movement data (Current Month Dr/Cr, for the "Company TB" tab) and
the closing-balance data (the main consolidated view) must reconcile
(Opening + Dr - Cr == Closing) or the two tabs will visibly disagree. The
only way to guarantee that is to derive both from the exact same query
result, fetched once, rather than re-running the balance backfill and the
movement backfill as two separate live queries at two different moments --
new transactions land on Databricks continuously, so two "point in time"
snapshots taken minutes apart will differ by the transactions posted in
between (same lesson as the 2026-09-04 December-close fix: fetch BS and PL
in the same sitting).

Net delta per (entity, account, ym) = debit - credit, which is exactly what
consolidated_trial_balance.sql's SUM(amount) computes -- so this reproduces
the same numbers as backfill_all_periods.py, just derived from movement
rows instead of a separate net-delta query.

Usage:
  python3 scripts/build_series_from_movement.py \
    --pages page_1.json ... \
    --out-dir /tmp/backfill_fresh
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ENTITIES_PATH = SCRIPT_DIR / "entities.json"

EARLIEST_YM = "2019-01"


def load_entities():
    with open(ENTITIES_PATH) as f:
        return json.load(f)["entities"]


def cell_value(cell):
    if "null_value" in cell:
        return None
    return cell.get("string_value")


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


def build_series(deltas, months, reset_yearly):
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
    return series


def period_key(fy, period):
    return f"{fy}-{period:02d}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pages", nargs="+", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    entities = load_entities()
    entity_by_code = {e["code"]: e for e in entities}

    idx, rows = load_pages(args.pages)

    latest_ym = max(r[idx["ym"]] for r in rows)
    months = month_range(EARLIEST_YM, latest_ym)

    bs_deltas = {}
    pl_deltas = {}
    names = {}
    for r in rows:
        entity = r[idx["entity_code"]]
        account = r[idx["mainaccountid"]]
        ym = r[idx["ym"]]
        names[account] = r[idx["mainaccountname"]]
        debit_acc = float(r[idx["debit_acc"]] or 0)
        credit_acc = float(r[idx["credit_acc"]] or 0)
        debit_rep = float(r[idx["debit_rep"]] or 0)
        credit_rep = float(r[idx["credit_rep"]] or 0)
        acc_delta = debit_acc - credit_acc
        rep_delta = debit_rep - credit_rep
        bucket = bs_deltas if int(account) < 4000000 else pl_deltas
        bucket.setdefault((entity, account), {})[ym] = (acc_delta, rep_delta)

    bs_series = build_series(bs_deltas, months, reset_yearly=False)
    pl_series = build_series(pl_deltas, months, reset_yearly=True)
    series = {**bs_series, **pl_series}

    # Earliest period each (entity, account) ever had real movement --
    # BS and PL account ranges never collide, so combining both delta maps
    # is safe. Used below to decide when a row should first appear, never
    # to hide it again afterward.
    first_ym = {key: min(ym_deltas.keys()) for key, ym_deltas in list(bs_deltas.items()) + list(pl_deltas.items())}

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    generated_keys = []
    for ym in months:
        y, m = ym.split("-")
        fy, period = int(y), int(m)

        accounts_by_id = {}
        control_totals = {code: {"accounting": 0.0, "reporting": 0.0} for code in entity_by_code}
        for (entity, account), per_month in series.items():
            if entity not in entity_by_code:
                continue
            # Include the row for every period from this (entity, account)'s
            # first-ever activity onward, even if its cumulative balance
            # happens to net to exactly zero in some later period (e.g. a
            # year-end intercompany settlement or closing entry) -- omitting
            # it would make the account silently disappear from that one
            # period and reappear later, which the tb collection must never
            # do (unlike currencytb, which intentionally drops near-zero
            # currency buckets). Only genuinely skip periods strictly
            # BEFORE the account's first transaction, when it didn't exist
            # yet.
            if ym < first_ym[(entity, account)]:
                continue
            acc, rep = per_month[ym]
            reporting_amt = rep
            if entity_by_code[entity].get("reportingCurrencyFallback"):
                reporting_amt = acc
            accounts_by_id.setdefault(account, {"mainAccountId": account, "mainAccountName": names[account], "byEntity": {}})
            accounts_by_id[account]["byEntity"][entity] = {"accounting": acc, "reporting": reporting_amt}
            control_totals[entity]["accounting"] += acc
            control_totals[entity]["reporting"] += reporting_amt

        warnings = []
        for code, totals in control_totals.items():
            if abs(totals["accounting"]) > 0.01:
                warnings.append(f"{code}: accountingcurrencyamount does not net to zero ({totals['accounting']:.2f})")

        out = {
            "fiscalYear": fy,
            "period": period,
            "generatedAt": generated_at,
            "accounts": sorted(accounts_by_id.values(), key=lambda a: a["mainAccountId"]),
            "entities": entities,
            "controlTotals": control_totals,
            "warnings": warnings,
        }
        key = period_key(fy, period)
        fname = out_dir / f"report_{key}.json"
        with open(fname, "w") as f:
            json.dump(out, f)
        generated_keys.append({"fiscalYear": fy, "period": period, "key": key})

    with open(out_dir / "summary.json", "w") as f:
        json.dump({"periods": generated_keys}, f, indent=2)

    print(f"Wrote {len(generated_keys)} periods to {out_dir}, generatedAt={generated_at}")


if __name__ == "__main__":
    main()
