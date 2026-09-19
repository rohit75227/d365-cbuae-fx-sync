#!/usr/bin/env python3
"""
Turn a raw claude-databricks-connector result from sql/customer_aging.sql
into the "customerAging" collection's document shape: a `customerAging`
period-style doc {generatedAt, shardCount, rowCount} plus
`customerAging/shards/<i>` docs each holding {rows: [...]}.

Unlike every other collection in this report, "customerAging" is NOT
period-scoped -- it's a live snapshot of currently-open receivables, and
this script always rebuilds the whole thing from one full fetch (no diffing
against a prior period; there's only ever one "current" snapshot).

Usage:
  python3 scripts/build_customer_aging.py raw_result.json --out-dir /tmp/aging
"""
import argparse
import json
import time
from pathlib import Path

MAX_DOC_BYTES = 200 * 1024


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
        raise SystemExit("Databricks result was TRUNCATED -- sql/customer_aging.sql needs pagination now.")
    columns = [c["name"] for c in raw["manifest"]["schema"]["columns"]]
    idx = {name: i for i, name in enumerate(columns)}
    data_rows = raw["result"].get("data_array")
    if data_rows is None:
        data_rows = raw["result"]["data_typed_array"]
    rows = []
    for row in data_rows:
        values = [cell_value(v) for v in row["values"]]
        rows.append({
            "legalEntity": values[idx["legal_entity"]],
            "customerAccount": values[idx["customer_account"]],
            "customerName": values[idx["customer_name"]] or "",
            "customerGroup": values[idx["customer_group"]] or "",
            "region": values[idx["region"]],
            "dueDate": (values[idx["due_date"]] or "")[:10],
            "remainingAccounting": float(values[idx["remaining_acc"]] or 0),
            "remainingReporting": float(values[idx["remaining_rep"]] or 0),
            "invoiceCount": int(values[idx["invoice_count"]] or 0),
        })
    return rows


def shard_rows(rows):
    shards, current = [], []
    for row in rows:
        current.append(row)
        if len(json.dumps({"rows": current})) > MAX_DOC_BYTES:
            current.pop()
            if not current:
                raise SystemExit("A single row exceeds the per-document size limit")
            shards.append(current)
            current = [row]
    if current:
        shards.append(current)
    return shards or [[]]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("raw_file")
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    with open(args.raw_file) as f:
        raw = json.load(f)

    rows = parse_rows(raw)
    shards = shard_rows(rows)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    doc = {
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "shardCount": len(shards),
        "rowCount": len(rows),
    }
    with open(out_dir / "doc.json", "w") as f:
        json.dump(doc, f)

    for i, shard in enumerate(shards):
        with open(out_dir / f"shard_{i}.json", "w") as f:
            json.dump({"rows": shard}, f)

    print(f"{len(rows)} rows -> {len(shards)} shard(s), generatedAt={doc['generatedAt']}")


if __name__ == "__main__":
    main()
