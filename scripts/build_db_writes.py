#!/usr/bin/env python3
"""
Turn sync_trial_balance.py's JSON output into a list of Artifact write_db
batch operations (set/update/delete dicts with collection, doc_id, data),
sharded to stay well under the 256 KiB per-document limit and the 50-writes-
per-batch limit of the Artifact tool's write_db(db_op="batch").

Usage:
  python3 scripts/sync_trial_balance.py --fiscal-year 2026 --period 6 \
    | python3 scripts/build_db_writes.py > writes.json

The Claude session driving the daily Routine reads writes.json and calls the
Artifact tool's write_db action once per batch of up to 50 entries (this
script already groups them that way in `batches`), against the trial
balance report's own artifact URL. This script has no Artifact tool access
itself -- it only prepares the payloads.
"""
import json
import sys

MAX_DOC_BYTES = 200 * 1024  # stay under the 256 KiB cap with headroom
MAX_WRITES_PER_BATCH = 50


def shard_accounts(accounts):
    shards = []
    current = []
    for acc in accounts:
        current.append(acc)
        # Rough size check; re-serializing every row is cheap at this scale
        # and safer than guessing a fixed row count per shard.
        if len(json.dumps({"rows": current})) > MAX_DOC_BYTES:
            current.pop()
            if not current:
                # A single account is, implausibly, over the cap by itself.
                raise SystemExit(f"Account {acc.get('mainAccountId')} alone exceeds the per-document size limit")
            shards.append(current)
            current = [acc]
    if current:
        shards.append(current)
    return shards


def main():
    report = json.load(sys.stdin)
    key = f"{report['fiscalYear']}-{report['period']:02d}"

    shards = shard_accounts(report["accounts"])

    writes = []
    writes.append({
        "op": "set",
        "collection": "tb",
        "doc_id": key,
        "data": {
            "fiscalYear": report["fiscalYear"],
            "period": report["period"],
            "generatedAt": report["generatedAt"],
            "warnings": report.get("warnings", []),
            "entities": report["entities"],
            "shardCount": len(shards),
        },
    })
    for i, shard in enumerate(shards):
        writes.append({
            "op": "set",
            "collection": f"tb/{key}/shards",
            "doc_id": str(i),
            "data": {"rows": shard},
        })

    # tb/index is updated separately (read-modify-write against whatever
    # periods already exist) -- emit it as its own note rather than a blind
    # overwrite, since a blind `set` here would wipe out other synced periods.
    index_upsert_note = {
        "fiscalYear": report["fiscalYear"],
        "period": report["period"],
        "key": key,
        "generatedAt": report["generatedAt"],
    }

    batches = [writes[i:i + MAX_WRITES_PER_BATCH] for i in range(0, len(writes), MAX_WRITES_PER_BATCH)]

    print(json.dumps({
        "periodKey": key,
        "batches": batches,
        "indexUpsert": index_upsert_note,
        "warnings": report.get("warnings", []),
    }, indent=2))


if __name__ == "__main__":
    main()
