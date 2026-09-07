#!/usr/bin/env python3
"""
Build every FY2019 P1 - present period for the "Intercompany Reconciliation"
tab from ONE fetch of sql/intercompany_movement.sql (monthly Dr/Cr movement
for the intercompany receivable (1122001-1122999) and payable
(2112001-2112999) account ranges, Kayali-named accounts already excluded by
the query itself).

Both ranges are pure Balance Sheet accounts (cumulative since inception, no
fiscal-year reset) -- so unlike backfill_all_periods.py there is no P&L
bucket and no year-reset logic: this simply forward-sums each (entity,
account)'s monthly movement into a running cumulative balance and takes a
snapshot at every period end. Because the whole history is fetched fresh in
one query (not blended with an old stored baseline), this is NOT the
"incremental build is unsound against backdating" trap documented in
docs/trial-balance-setup.md -- it's algebraically identical to running a
direct cumulative-to-date query at every period end, just far cheaper.

An account is DROPPED from a period's output entirely if every entity's
balance is ~0.00 that period (report requirement: no zero-balance rows) --
unlike the main tb collection, which keeps zero accounts so they don't
disappear and reappear across periods.

Usage:
  python3 scripts/build_intercompany_periods.py raw_result.json \
    --out-dir /tmp/intercompany_out
"""
import argparse
import json
import sys
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
    if "string_value" in cell:
        return cell["string_value"]
    if "str" in cell:
        return cell["str"]
    return None


def parse_rows(raw):
    if raw["manifest"].get("truncated") or raw.get("truncated"):
        raise SystemExit("Result was TRUNCATED -- this query's grain was expected to stay under the 12,288-row cap.")
    columns = [c["name"] for c in raw["manifest"]["schema"]["columns"]]
    idx = {name: i for i, name in enumerate(columns)}
    data_rows = raw["result"].get("data_array")
    if data_rows is None:
        data_rows = raw["result"]["data_typed_array"]
    rows = []
    for row in data_rows:
        rows.append([cell_value(v) for v in row["values"]])
    return idx, rows


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


def account_kind(main_account_id):
    n = int(main_account_id)
    if 1122001 <= n <= 1122999:
        return "receivable"
    if 2112001 <= n <= 2112999:
        return "payable"
    raise SystemExit(f"Unexpected mainaccountid outside both intercompany ranges: {main_account_id}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("raw_file")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--latest-ym", required=True, help="last period (YYYY-MM) to snapshot, e.g. the current tb index's latest key")
    args = parser.parse_args()

    with open(args.raw_file) as f:
        raw = json.load(f)
    idx, rows = parse_rows(raw)

    # movement[(entity, account)][ym] = {debit_acc, credit_acc, debit_rep, credit_rep}
    movement = {}
    names = {}
    for r in rows:
        entity = r[idx["entity_code"]]
        account = r[idx["mainaccountid"]]
        ym = r[idx["ym"]]
        names[account] = r[idx["mainaccountname"]]
        key = (entity, account)
        movement.setdefault(key, {})[ym] = {
            "debit_acc": float(r[idx["debit_acc"]] or 0),
            "credit_acc": float(r[idx["credit_acc"]] or 0),
            "debit_rep": float(r[idx["debit_rep"]] or 0),
            "credit_rep": float(r[idx["credit_rep"]] or 0),
        }

    months = month_range(EARLIEST_YM, args.latest_ym)

    # running[(entity, account)] = {accounting, reporting}, forward-summed month by month
    running = {}
    # snapshots[ym][(entity, account)] = {accounting, reporting}
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
        y, m = ym.split("-")
        fy, period = int(y), int(m)
        by_account = {}
        for (entity, account), bal in snapshots[ym].items():
            acc = by_account.setdefault(account, {
                "mainAccountId": account,
                "mainAccountName": names.get(account, ""),
                "kind": account_kind(account),
                "byEntity": {},
            })
            acc["byEntity"][entity] = {"accounting": bal["accounting"], "reporting": bal["reporting"]}

        accounts = sorted(by_account.values(), key=lambda a: (a["kind"], a["mainAccountId"]))
        out = {"fiscalYear": fy, "period": period, "accounts": accounts}
        fname = out_dir / f"report_{fy}-{period:02d}.json"
        with open(fname, "w") as f:
            json.dump(out, f)
        periods_written.append(f"{fy}-{period:02d}")

    with open(out_dir / "summary.json", "w") as f:
        json.dump({"periods": periods_written}, f, indent=2)

    print(f"Wrote {len(periods_written)} intercompany periods to {out_dir}", file=sys.stderr)


if __name__ == "__main__":
    main()
