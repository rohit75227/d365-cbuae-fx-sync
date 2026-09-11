#!/usr/bin/env python3
"""
Build every FY2019 P1 - present period for the "Vendor Balance" / "Customer
Balance" tabs from ONE fetch of sql/vendor_balance.sql,
sql/vendor_balance_by_currency.sql, sql/customer_balance.sql, or
sql/customer_balance_by_currency.sql.

Both AP (vendor) and AR (customer) subledger balances are pure Balance
Sheet in nature -- cumulative since ledger inception, no fiscal-year
reset -- so this mirrors scripts/build_intercompany_periods.py exactly:
forward-sum each (entity, account[, currency])'s monthly movement into a
running cumulative balance and snapshot it at every period end. A row is
DROPPED from a period's output entirely if its balance is ~0.00 that
period (report requirement, per the Vendor/Customer Balance tab's own
footer: "only vendors/customers with a nonzero balance that period are
listed").

Usage:
  python3 scripts/build_party_balance_periods.py raw1.json [raw2.json ...] \
    --kind vendor --grain balance --out-dir /tmp/vendor_balance_out --latest-ym 2026-09
  python3 scripts/build_party_balance_periods.py raw1.json [raw2.json ...] \
    --kind customer --grain currency --out-dir /tmp/customer_currency_out --latest-ym 2026-09
"""
import argparse
import json
import sys
from pathlib import Path

EARLIEST_YM = "2019-01"


def cell_value(cell):
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("raw_files", nargs="+")
    parser.add_argument("--kind", required=True, choices=["vendor", "customer"])
    parser.add_argument("--grain", required=True, choices=["balance", "currency"])
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--latest-ym", required=True)
    args = parser.parse_args()

    account_field = "vendor_account" if args.kind == "vendor" else "customer_account"
    name_field = "vendor_name" if args.kind == "vendor" else "customer_name"
    group_field = "vendor_group" if args.kind == "vendor" else "customer_group"
    out_account_key = "vendorAccount" if args.kind == "vendor" else "customerAccount"
    out_name_key = "vendorName" if args.kind == "vendor" else "customerName"
    out_group_key = "vendorGroup" if args.kind == "vendor" else "customerGroup"

    idx, rows = load_pages(args.raw_files)
    months = month_range(EARLIEST_YM, args.latest_ym)

    names = {}
    groups = {}

    if args.grain == "balance":
        # movement[(entity, account)][ym] = {debit_acc, credit_acc, debit_rep, credit_rep}
        movement = {}
        for r in rows:
            entity = r[idx["legal_entity"]]
            account = r[idx[account_field]]
            ym = r[idx["ym"]]
            names[(entity, account)] = r[idx[name_field]]
            groups[(entity, account)] = r[idx[group_field]]
            movement.setdefault((entity, account), {})[ym] = {
                "debit_acc": float(r[idx["debit_acc"]] or 0),
                "credit_acc": float(r[idx["credit_acc"]] or 0),
                "debit_rep": float(r[idx["debit_rep"]] or 0),
                "credit_rep": float(r[idx["credit_rep"]] or 0),
            }

        running = {}
        snapshots = {ym: {} for ym in months}
        for ym in months:
            for key in movement:
                m = movement[key].get(ym)
                if not m:
                    continue
                bal = running.setdefault(key, {"accounting": 0.0, "reporting": 0.0})
                bal["accounting"] += m["debit_acc"] - m["credit_acc"]
                bal["reporting"] += m["debit_rep"] - m["credit_rep"]
            for key, bal in running.items():
                if abs(bal["accounting"]) > 0.01 or abs(bal["reporting"]) > 0.01:
                    snapshots[ym][key] = {"accounting": bal["accounting"], "reporting": bal["reporting"]}

        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        periods_written = []
        for ym in months:
            fy, period = int(ym[:4]), int(ym[5:7])
            party_rows = []
            for (entity, account), bal in snapshots[ym].items():
                party_rows.append({
                    "legalEntity": entity,
                    out_account_key: account,
                    out_name_key: names.get((entity, account)) or "",
                    out_group_key: groups.get((entity, account)) or "",
                    "accounting": bal["accounting"],
                    "reporting": bal["reporting"],
                })
            party_rows.sort(key=lambda r: (r["legalEntity"], r[out_account_key]))
            fname = out_dir / f"report_{ym}.json"
            with open(fname, "w") as f:
                json.dump({"fiscalYear": fy, "period": period, "rows": party_rows}, f)
            periods_written.append(ym)

    else:  # currency grain
        movement = {}
        for r in rows:
            entity = r[idx["legal_entity"]]
            account = r[idx[account_field]]
            ccy = r[idx["txn_ccy"]]
            ym = r[idx["ym"]]
            names[(entity, account)] = r[idx[name_field]]
            groups[(entity, account)] = r[idx[group_field]]
            movement.setdefault((entity, account, ccy), {})[ym] = {
                "debit_txn": float(r[idx["debit_txn"]] or 0),
                "credit_txn": float(r[idx["credit_txn"]] or 0),
            }

        running = {}
        snapshots = {ym: {} for ym in months}
        for ym in months:
            for key in movement:
                m = movement[key].get(ym)
                if not m:
                    continue
                running[key] = running.get(key, 0.0) + m["debit_txn"] - m["credit_txn"]
            for key, amount in running.items():
                if abs(amount) > 0.01:
                    snapshots[ym][key] = amount

        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        periods_written = []
        for ym in months:
            fy, period = int(ym[:4]), int(ym[5:7])
            party_rows = []
            for (entity, account, ccy), amount in snapshots[ym].items():
                party_rows.append({
                    "legalEntity": entity,
                    out_account_key: account,
                    out_name_key: names.get((entity, account)) or "",
                    out_group_key: groups.get((entity, account)) or "",
                    "currency": ccy,
                    "amount": amount,
                })
            party_rows.sort(key=lambda r: (r["legalEntity"], r[out_account_key], r["currency"]))
            fname = out_dir / f"report_{ym}.json"
            with open(fname, "w") as f:
                json.dump({"fiscalYear": fy, "period": period, "rows": party_rows}, f)
            periods_written.append(ym)

    with open(out_dir / "summary.json", "w") as f:
        json.dump({"periods": periods_written}, f, indent=2)
    print(f"Wrote {len(periods_written)} {args.kind}/{args.grain} periods to {out_dir}", file=sys.stderr)


if __name__ == "__main__":
    main()
