#!/usr/bin/env python3
"""
Build the "By Currency" view's per-period closing-balance series: same
Balance-Sheet-cumulative / P&L-fiscal-year-reset reconstruction as
build_series_from_movement.py, but keyed by (entity, account, transaction
currency) instead of (entity, account) -- so one main account can show
multiple rows, one per currency it was actually posted in.

Source: sql/monthly_movement_by_currency.sql (adds transactioncurrencycode
to the grain). Net delta per (entity, account, currency, ym) = debit -
credit, exactly matching how the main trial balance and the "Company TB"
movement view compute their numbers, so a currency-view account's rows sum
to the same closing balance already published in the "tb" collection.

Usage:
  python3 scripts/build_currency_series.py --pages page_1.json ... --out-dir /tmp/currency_out
"""
import argparse
import json
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
        ccy = r[idx["txn_ccy"]]
        names[account] = r[idx["mainaccountname"]]
        debit_acc = float(r[idx["debit_acc"]] or 0)
        credit_acc = float(r[idx["credit_acc"]] or 0)
        debit_rep = float(r[idx["debit_rep"]] or 0)
        credit_rep = float(r[idx["credit_rep"]] or 0)
        acc_delta = debit_acc - credit_acc
        rep_delta = debit_rep - credit_rep
        bucket = bs_deltas if int(account) < 4000000 else pl_deltas
        bucket.setdefault((entity, account, ccy), {})[ym] = (acc_delta, rep_delta)

    bs_series = build_series(bs_deltas, months, reset_yearly=False)
    pl_series = build_series(pl_deltas, months, reset_yearly=True)
    series = {**bs_series, **pl_series}

    generated_keys = []
    for ym in months:
        y, m = ym.split("-")
        fy, period = int(y), int(m)

        # rows keyed by (account, ccy) -> {mainAccountId, mainAccountName, txnCurrency, byEntity}
        rows_by_key = {}
        for (entity, account, ccy), per_month in series.items():
            if entity not in entity_by_code:
                continue
            acc, rep = per_month[ym]
            if abs(acc) < 0.005 and abs(rep) < 0.005:
                continue
            reporting_amt = rep
            if entity_by_code[entity].get("reportingCurrencyFallback"):
                reporting_amt = acc
            key = (account, ccy)
            rows_by_key.setdefault(key, {
                "mainAccountId": account, "mainAccountName": names[account],
                "txnCurrency": ccy, "byEntity": {},
            })
            rows_by_key[key]["byEntity"][entity] = {"accounting": acc, "reporting": reporting_amt}

        out_rows = sorted(rows_by_key.values(), key=lambda r: (r["mainAccountId"], r["txnCurrency"]))
        out = {"fiscalYear": fy, "period": period, "rows": out_rows}
        key = period_key(fy, period)
        fname = out_dir / f"currency_{key}.json"
        with open(fname, "w") as f:
            json.dump(out, f)
        generated_keys.append(key)

    with open(out_dir / "summary.json", "w") as f:
        json.dump({"periods": generated_keys}, f, indent=2)

    print(f"Wrote {len(generated_keys)} periods to {out_dir}")


if __name__ == "__main__":
    main()
