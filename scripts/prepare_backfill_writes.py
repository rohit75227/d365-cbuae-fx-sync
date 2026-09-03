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

HBCB_ADJ = {
    "entity": "HBCB", "account": "3141001", "account_name": "Retained Earnings - Accumulated",
    "accounting_delta": -278118823.426, "reporting_delta": -278118823.426,
    "reason": "Simulated FY2025 year-end close (not yet posted in D365) -- transfers HBCB's unclosed FY2024/2025 P&L into Retained Earnings",
}
HBUK_ADJ = {
    "entity": "HBUK", "account": "3141001", "account_name": "Retained Earnings - Accumulated",
    "accounting_delta": 18000.00, "reporting_delta": 24683.40,
    "reason": "Simulated correction (not yet posted in D365) -- HBUK's FY2025 close (voucher clguk25v2) under-reversed account 6210008 Other Marketing - Influencer by exactly 18,000.00; this transfers the missing amount into Retained Earnings as if the close had been correct",
}

MAX_DOC_BYTES = 200 * 1024
MAX_WRITES_PER_BATCH = 50
MAX_BATCH_BYTES = 800 * 1024  # stay well under the 1 MiB per-request limit


def apply_adjustment(report, adj):
    totals = report["controlTotals"].get(adj["entity"], {"accounting": 0.0, "reporting": 0.0})
    if abs(totals["accounting"]) <= 0.01:
        return  # already balanced for this period -- nothing pending yet, don't touch it

    account = next((a for a in report["accounts"] if a["mainAccountId"] == adj["account"]), None)
    if account is None:
        account = {"mainAccountId": adj["account"], "mainAccountName": adj["account_name"], "byEntity": {}}
        report["accounts"].append(account)
        report["accounts"].sort(key=lambda a: a["mainAccountId"])

    cell = account["byEntity"].setdefault(adj["entity"], {"accounting": 0.0, "reporting": 0.0})
    cell["accounting"] = (cell.get("accounting") or 0.0) + adj["accounting_delta"]
    cell["reporting"] = (cell.get("reporting") or 0.0) + adj["reporting_delta"]

    report.setdefault("simulatedAdjustments", []).append({
        "entity": adj["entity"], "mainAccountId": adj["account"], "mainAccountName": adj["account_name"],
        "accountingDelta": adj["accounting_delta"], "reportingDelta": adj["reporting_delta"], "reason": adj["reason"],
    })

    totals["accounting"] += adj["accounting_delta"]
    totals["reporting"] += adj["reporting_delta"]
    report["controlTotals"][adj["entity"]] = totals

    report["warnings"] = [w for w in report["warnings"] if not w.startswith(f"{adj['entity']}:")]
    if abs(totals["accounting"]) > 0.01:
        report["warnings"].append(f"{adj['entity']}: accountingcurrencyamount does not net to zero ({totals['accounting']:.2f})")
    report["warnings"].append(
        f"{adj['entity']}: includes a SIMULATED adjustment of {adj['accounting_delta']:,.2f} to "
        f"{adj['account']} \"{adj['account_name']}\" -- {adj['reason']}"
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

        apply_adjustment(report, HBCB_ADJ)
        apply_adjustment(report, HBUK_ADJ)

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
