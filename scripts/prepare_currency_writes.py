#!/usr/bin/env python3
"""
Shard the per-period currency_<key>.json files (from build_currency_series.py)
into write_db-ready "period doc" + "shard doc" files for the "currencytb"
collection (the "By Currency" view), mirroring prepare_movement_writes.py.

Usage:
  python3 scripts/prepare_currency_writes.py --in-dir /tmp/currency_out --out-dir /tmp/currency_out/writes
"""
import argparse
import json
from pathlib import Path

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
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    in_dir = Path(args.in_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(in_dir / "summary.json") as f:
        periods = json.load(f)["periods"]

    all_writes = []

    for key in periods:
        with open(in_dir / f"currency_{key}.json") as f:
            report = json.load(f)

        shards = shard_rows(report["rows"])
        period_doc = {"fiscalYear": report["fiscalYear"], "period": report["period"], "shardCount": len(shards)}

        period_file = out_dir / f"period_{key}.json"
        with open(period_file, "w") as f:
            json.dump(period_doc, f)
        all_writes.append({"op": "set", "collection": "currencytb", "doc_id": key, "file_path": str(period_file), "_bytes": period_file.stat().st_size})

        for i, shard in enumerate(shards):
            shard_file = out_dir / f"shard_{key}_{i}.json"
            with open(shard_file, "w") as f:
                json.dump({"rows": shard}, f)
            all_writes.append({"op": "set", "collection": f"currencytb/{key}/shards", "doc_id": str(i), "file_path": str(shard_file), "_bytes": shard_file.stat().st_size})

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

    print(f"{len(periods)} periods, {len(all_writes)} document writes across {len(batches)} batches")


if __name__ == "__main__":
    main()
