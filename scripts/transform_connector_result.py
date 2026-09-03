#!/usr/bin/env python3
"""
Turn a raw result from the claude-databricks-connector's execute_sql_read_only
tool (saved to a file — large results get written to disk rather than
returned inline) into the same report JSON shape sync_trial_balance.py used
to produce: { accounts, entities, controlTotals, fiscalYear, period,
generatedAt, warnings }.

The connector's JSON_ARRAY result format encodes every cell as
{"string_value": "..."} or {"null_value": "NULL_VALUE"}, in the column
order given by manifest.schema.columns -- this only knows how to read that
shape (observed directly against a live query in this session), not the
raw Databricks SQL Statement Execution API shape scripts/sync_trial_balance.py
used when talking to Databricks directly over REST.

Usage:
  python3 scripts/transform_connector_result.py raw_result.json \
    --fiscal-year 2026 --period 8 --period-end-exclusive 2026-09-01 \
    > report.json
"""
import argparse
import json
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ENTITIES_PATH = SCRIPT_DIR / "entities.json"


def load_entities():
    with open(ENTITIES_PATH) as f:
        return json.load(f)["entities"]


def cell_value(cell):
    if "null_value" in cell:
        return None
    return cell.get("string_value")


def parse_rows(raw):
    if raw["manifest"].get("truncated") or raw.get("truncated"):
        raise SystemExit(
            "Databricks result was TRUNCATED. This query's grain "
            "(mainaccount x entity) was expected to stay under the "
            "12,288-row cap -- if it didn't, use the ROW_NUMBER() "
            "pagination pattern from the GL Reporting project instructions "
            "before trusting this output."
        )
    columns = [c["name"] for c in raw["manifest"]["schema"]["columns"]]
    idx = {name: i for i, name in enumerate(columns)}
    rows = []
    for row in raw["result"]["data_array"]:
        values = [cell_value(v) for v in row["values"]]
        rows.append(values)
    return idx, rows


def build_report(idx, rows, entities):
    entity_by_code = {e["code"]: e for e in entities}
    accounts = {}
    control_totals = {code: {"accounting": 0.0, "reporting": 0.0} for code in entity_by_code}
    unknown_entities = set()

    for row in rows:
        mainaccountid = row[idx["mainaccountid"]]
        mainaccountname = row[idx["mainaccountname"]]
        entity_code = row[idx["entity_code"]]
        accounting_amt = float(row[idx["accountingcurrencyamount"]] or 0)
        reporting_raw = row[idx["reportingcurrencyamount"]]
        reporting_amt = float(reporting_raw) if reporting_raw is not None else None

        if entity_code not in entity_by_code:
            unknown_entities.add(entity_code)
            continue

        if reporting_amt is None and entity_by_code[entity_code].get("reportingCurrencyFallback"):
            reporting_amt = accounting_amt

        acc = accounts.setdefault(mainaccountid, {"mainAccountId": mainaccountid, "mainAccountName": mainaccountname, "byEntity": {}})
        acc["byEntity"][entity_code] = {"accounting": accounting_amt, "reporting": reporting_amt}

        control_totals[entity_code]["accounting"] += accounting_amt
        if reporting_amt is not None:
            control_totals[entity_code]["reporting"] += reporting_amt

    warnings = []
    for code, totals in control_totals.items():
        if abs(totals["accounting"]) > 0.01:
            warnings.append(f"{code}: accountingcurrencyamount does not net to zero ({totals['accounting']:.2f})")
    if unknown_entities:
        warnings.append(f"Rows for entities not in entities.json were dropped: {sorted(unknown_entities)}")

    return {
        "accounts": sorted(accounts.values(), key=lambda a: a["mainAccountId"]),
        "entities": entities,
        "controlTotals": control_totals,
        "warnings": warnings,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("raw_file")
    parser.add_argument("--fiscal-year", type=int, required=True)
    parser.add_argument("--period", type=int, required=True)
    args = parser.parse_args()

    with open(args.raw_file) as f:
        raw = json.load(f)

    entities = load_entities()
    idx, rows = parse_rows(raw)
    report = build_report(idx, rows, entities)
    report["fiscalYear"] = args.fiscal_year
    report["period"] = args.period
    report["generatedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    print(json.dumps(report))
    for w in report["warnings"]:
        print(w, file=sys.stderr)


if __name__ == "__main__":
    main()
