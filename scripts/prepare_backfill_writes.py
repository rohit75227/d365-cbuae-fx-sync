#!/usr/bin/env python3
"""
Take the 93 report_<key>.json files from backfill_all_periods.py, apply the
HBCB/HBUK simulated adjustments to whichever periods actually need them
(same threshold logic as the daily Routine -- only when the raw control
total is still materially off), then write out per-period "period doc" and
"shard doc" JSON files ready for Artifact write_db (file_path form), plus a
manifest of write_db batch commands (<=50 writes each) and an updated
tb/index document covering every period.

Usage:
  python3 scripts/prepare_backfill_writes.py --in-dir /tmp/backfill --out-dir /tmp/backfill/writes
"""
import argparse
import json
from pathlib import Path

ENTITIES_TO_AUTO_SIMULATE = {
    "HBCB": {
        "account": "3141001", "account_name": "Retained Earnings - Accumulated",
        "reason": "Simulated year-end close (not yet posted in D365) -- transfers HBCB's unclosed prior-year P&L into Retained Earnings. Sized dynamically per period: this period's own raw control-total gap, not a fixed historical figure, because the gap grows as more fiscal years go unclosed (smaller in early periods, larger by FY2026).",
    },
    "HBUK": {
        "account": "3141001", "account_name": "Retained Earnings - Accumulated",
        "reason": "Simulated correction (not yet posted in D365) -- HBUK's FY2025 close under-reversed something; FY2025 P12 itself already nets to 0.00, this gap is specific to later periods and not fully isolated as of 2026-09-04 (see docs/trial-balance-setup.md). Sized dynamically per period, not a fixed figure.",
    },
    "HBFR": {
        "account": "3141001", "account_name": "Retained Earnings - Accumulated",
        "reason": "Simulated year-end close correction (not yet posted in D365) -- transfers HBFR's unclosed FY2020 currency-revaluation activity into Retained Earnings. Investigated 2026-09-08: HBFR's accounting-currency (EUR) total always ties to exactly 0.00, but several 31-Dec-2020 revaluation vouchers (HBFR-000001, HBFR-ERAV-*, HBFR-EXV-0000001/HBFR-PAY-0000006) posted $0 accounting-currency / nonzero reporting-currency (USD) entries -- some as late as 26-Jan-2022, a day after FY2020's closing voucher clgfr20v5 already ran on 25-Jan-2022 -- so they were never swept into Retained Earnings. Confirmed live across every stored period from 2021-01 through 2026-09: the raw gap stays essentially flat at ~2,443.07 the entire time (does not compound year over year), so this adjustment is sized dynamically from each period's own raw total rather than hardcoded, but in practice lands on the same figure every period.",
    },
}

MAX_DOC_BYTES = 200 * 1024
MAX_WRITES_PER_BATCH = 50
MAX_BATCH_BYTES = 800 * 1024  # stay well under the 1 MiB per-request limit


def apply_adjustment(report, entity, spec):
    """Plug exactly this period's own raw gap for `entity` -- NEVER a fixed
    dollar amount copied from another period. The real gap (an unclosed
    prior year's P&L sitting in Retained Earnings) grows as more fiscal
    years go unclosed, so a fixed figure that's correct for one period
    massively overcorrects a different period (caught 2026-09-04: applying
    the FY2026-sized HBCB adjustment to Dec 2025 turned a +2.39M gap into a
    -275.7M one)."""
    totals = report["controlTotals"].get(entity, {"accounting": 0.0, "reporting": 0.0})
    if abs(totals["accounting"]) <= 0.01 and abs(totals["reporting"]) <= 0.01:
        return  # already balanced for this period -- nothing pending yet, don't touch it

    accounting_delta = -totals["accounting"]
    reporting_delta = -totals["reporting"]

    account = next((a for a in report["accounts"] if a["mainAccountId"] == spec["account"]), None)
    if account is None:
        account = {"mainAccountId": spec["account"], "mainAccountName": spec["account_name"], "byEntity": {}}
        report["accounts"].append(account)
        report["accounts"].sort(key=lambda a: a["mainAccountId"])

    cell = account["byEntity"].setdefault(entity, {"accounting": 0.0, "reporting": 0.0})
    cell["accounting"] = (cell.get("accounting") or 0.0) + accounting_delta
    cell["reporting"] = (cell.get("reporting") or 0.0) + reporting_delta

    report.setdefault("simulatedAdjustments", []).append({
        "entity": entity, "mainAccountId": spec["account"], "mainAccountName": spec["account_name"],
        "accountingDelta": accounting_delta, "reportingDelta": reporting_delta, "reason": spec["reason"],
    })

    report["controlTotals"][entity] = {"accounting": 0.0, "reporting": 0.0}  # plugged exactly, by construction

    report["warnings"] = [w for w in report["warnings"] if not w.startswith(f"{entity}:")]
    report["warnings"].append(
        f"{entity}: includes a SIMULATED adjustment of {accounting_delta:,.2f} to "
        f"{spec['account']} \"{spec['account_name']}\" -- {spec['reason']}"
    )


def shard_accounts(accounts):
    shards, current = [], []
    for acc in accounts:
        current.append(acc)
        if len(json.dumps({"rows": current})) > MAX_DOC_BYTES:
            current.pop()
            if not current:
                raise SystemExit(f"Account {acc.get('mainAccountId')} alone exceeds the per-document size limit")
            shards.append(current)
            current = [acc]
    if current:
        shards.append(current)
    return shards or [[]]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--in-dir", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    in_dir = Path(args.in_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(in_dir / "summary.json") as f:
        periods = json.load(f)["periods"]

    all_writes = []  # list of {op, collection, doc_id, file_path}
    index_periods = []

    for p in periods:
        key = p["key"]
        with open(in_dir / f"report_{key}.json") as f:
            report = json.load(f)

        for entity, spec in ENTITIES_TO_AUTO_SIMULATE.items():
            apply_adjustment(report, entity, spec)

        shards = shard_accounts(report["accounts"])
        period_doc = {
            "fiscalYear": report["fiscalYear"], "period": report["period"], "generatedAt": report["generatedAt"],
            "warnings": report.get("warnings", []), "entities": report["entities"], "shardCount": len(shards),
        }
        if report.get("simulatedAdjustments"):
            period_doc["simulatedAdjustments"] = report["simulatedAdjustments"]

        period_file = out_dir / f"period_{key}.json"
        with open(period_file, "w") as f:
            json.dump(period_doc, f)
        all_writes.append({"op": "set", "collection": "tb", "doc_id": key, "file_path": str(period_file), "_bytes": period_file.stat().st_size})

        for i, shard in enumerate(shards):
            shard_file = out_dir / f"shard_{key}_{i}.json"
            with open(shard_file, "w") as f:
                json.dump({"rows": shard}, f)
            all_writes.append({"op": "set", "collection": f"tb/{key}/shards", "doc_id": str(i), "file_path": str(shard_file), "_bytes": shard_file.stat().st_size})

        index_periods.append({"fiscalYear": report["fiscalYear"], "period": report["period"], "key": key, "generatedAt": report["generatedAt"]})

    batches = []
    current, current_bytes = [], 0
    for w in all_writes:
        wbytes = w.pop("_bytes")
        if current and (len(current) >= MAX_WRITES_PER_BATCH or current_bytes + wbytes > MAX_BATCH_BYTES):
            batches.append(current)
            current, current_bytes = [], 0
        current.append(w)
        current_bytes += wbytes
    if current:
        batches.append(current)

    with open(out_dir / "batches.json", "w") as f:
        json.dump({"batches": batches, "totalWrites": len(all_writes)}, f, indent=2)

    with open(out_dir / "index_doc.json", "w") as f:
        json.dump({"periods": index_periods, "updatedAt": "2026-09-03T19:00:00Z"}, f, indent=2)

    print(f"{len(periods)} periods, {len(all_writes)} document writes across {len(batches)} batches", file=None)


if __name__ == "__main__":
    main()
