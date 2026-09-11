#!/usr/bin/env python3
"""
Shard the per-period report_<ym>.json files from build_party_balance_periods.py
into write_db-ready "period doc" + "shard doc" files for the "vendor" or
"customer" collection, mirroring prepare_intercompany_writes.py.

Balance-grain output writes to <collection>/<key>/shards (shardCount on the
period doc); currency-grain output writes to <collection>/<key>/currency-shards
(currencyShardCount on the period doc) -- both grains share one period doc
per key, so run this once for balance and once for currency into the SAME
--out-dir and it merges the two shard sets into one set of period docs.

Usage:
  python3 scripts/prepare_party_balance_writes.py --in-dir /tmp/vendor_balance_out \
    --collection vendor --grain balance --out-dir /tmp/vendor_out/writes
  python3 scripts/prepare_party_balance_writes.py --in-dir /tmp/vendor_currency_out \
    --collection vendor --grain currency --out-dir /tmp/vendor_out/writes
"""
import argparse
import json
from pathlib import Path
from datetime import datetime, timezone

MAX_DOC_BYTES = 200 * 1024
MAX_WRITES_PER_BATCH = 50
MAX_BATCH_BYTES = 800 * 1024


def shard_rows(rows):
    shards, current = [], []
    for row in rows:
        current.append(row)
        if len(json.dumps({"rows": current})) > MAX_DOC_BYTES:
            current.pop()
            if not current:
                raise SystemExit(f"Row alone exceeds the per-document size limit: {row}")
            shards.append(current)
            current = [row]
    if current:
        shards.append(current)
    return shards or [[]]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--in-dir", required=True)
    parser.add_argument("--collection", required=True, choices=["vendor", "customer"])
    parser.add_argument("--grain", required=True, choices=["balance", "currency"])
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    in_dir = Path(args.in_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(in_dir / "summary.json") as f:
        periods = json.load(f)["periods"]

    shard_collection = "shards" if args.grain == "balance" else "currency-shards"
    count_field = "shardCount" if args.grain == "balance" else "currencyShardCount"
    count_field_alt = ("vendorCount" if args.collection == "vendor" else "customerCount") if args.grain == "balance" else None
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    all_writes = []
    period_meta = {}

    for ym in periods:
        with open(in_dir / f"report_{ym}.json") as f:
            report = json.load(f)
        rows = report["rows"]
        shards = shard_rows(rows)

        period_doc_path = out_dir / f"period_{ym}.json"
        if period_doc_path.exists():
            with open(period_doc_path) as f:
                period_doc = json.load(f)
        else:
            period_doc = {"fiscalYear": report["fiscalYear"], "period": report["period"], "generatedAt": generated_at}

        period_doc[count_field] = len(shards)
        if count_field_alt:
            period_doc[count_field_alt] = len(rows)

        with open(period_doc_path, "w") as f:
            json.dump(period_doc, f)
        all_writes.append({"op": "set", "collection": args.collection, "doc_id": ym, "file_path": str(period_doc_path), "_bytes": period_doc_path.stat().st_size})

        for i, shard in enumerate(shards):
            shard_file = out_dir / f"{shard_collection.replace('-', '_')}_{ym}_{i}.json"
            with open(shard_file, "w") as f:
                json.dump({"rows": shard}, f)
            all_writes.append({"op": "set", "collection": f"{args.collection}/{ym}/{shard_collection}", "doc_id": str(i), "file_path": str(shard_file), "_bytes": shard_file.stat().st_size})

        period_meta[ym] = True

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

    with open(out_dir / f"batches_{args.grain}.json", "w") as f:
        json.dump({"batches": batches, "totalWrites": len(all_writes)}, f, indent=2)

    print(f"{len(periods)} periods, {len(all_writes)} document writes across {len(batches)} batches ({args.grain})")


if __name__ == "__main__":
    main()
