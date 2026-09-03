#!/usr/bin/env python3
"""
Consolidated Trial Balance sync: Databricks -> report JSON.

Runs sql/consolidated_trial_balance.sql for a given fiscal year/period against
the hb_catalog.db_bronze_d365 bronze layer, applies the four mandatory GL
rules from the "GL Reporting from D365 Bronze Layer" project, pivots the
result into Main Account x Company, and prints a single JSON document to
stdout. The caller (a daily Routine running inside a Claude session) reads
that JSON and writes it into the trial-balance report Artifact's database
with the Artifact tool's write_db action -- this script has no knowledge of
the report/Artifact itself, it only talks to Databricks.

Auth: prefers a Databricks service-principal OAuth M2M client (least
privilege, no dependency on any one person's account). Falls back to a
personal access token if the M2M env vars are not set, for initial testing.

Required env vars (set on the Claude Code Environment, never committed):
  DATABRICKS_HOST            e.g. https://hudabeauty.cloud.databricks.com
  DATABRICKS_WAREHOUSE_ID    SQL warehouse id (from the warehouse's Connection
                              Details tab; NOT the same as the http_path)
  DATABRICKS_CLIENT_ID       service principal application id   (OAuth M2M)
  DATABRICKS_CLIENT_SECRET   service principal secret            (OAuth M2M)
  -- OR, instead of the two above --
  DATABRICKS_TOKEN           a personal access token (PAT)

Usage:
  python3 sync_trial_balance.py --fiscal-year 2026 --period 6
  python3 sync_trial_balance.py --fiscal-year 2026 --period 6 --dry-run
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
SQL_PATH = SCRIPT_DIR.parent / "sql" / "consolidated_trial_balance.sql"
ENTITIES_PATH = SCRIPT_DIR / "entities.json"

STATEMENT_POLL_INTERVAL_SECONDS = 2
STATEMENT_TIMEOUT_SECONDS = 120


def load_entities():
    with open(ENTITIES_PATH) as f:
        return json.load(f)["entities"]


def load_sql():
    text = SQL_PATH.read_text()
    # Drop full-line comments, then take the first ";"-terminated statement
    # (the file's trailing control-total notes are commentary only, no SQL).
    code_lines = [l for l in text.splitlines() if not l.strip().startswith("--")]
    code = "\n".join(code_lines)
    statement = code.split(";")[0].strip()
    if not statement.upper().startswith(("WITH", "SELECT")):
        raise RuntimeError(f"Could not find a SELECT/WITH statement in {SQL_PATH}")
    return statement


def get_m2m_token(host, client_id, client_secret):
    resp = requests.post(
        f"{host}/oidc/v1/token",
        auth=(client_id, client_secret),
        data={"grant_type": "client_credentials", "scope": "all-apis"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def get_auth_header():
    host = os.environ.get("DATABRICKS_HOST", "").rstrip("/")
    if not host:
        raise SystemExit("DATABRICKS_HOST is not set")

    client_id = os.environ.get("DATABRICKS_CLIENT_ID")
    client_secret = os.environ.get("DATABRICKS_CLIENT_SECRET")
    token = os.environ.get("DATABRICKS_TOKEN")

    if client_id and client_secret:
        access_token = get_m2m_token(host, client_id, client_secret)
    elif token:
        access_token = token
    else:
        raise SystemExit(
            "No Databricks credentials found. Set DATABRICKS_CLIENT_ID + "
            "DATABRICKS_CLIENT_SECRET (preferred, service principal OAuth "
            "M2M) or DATABRICKS_TOKEN (PAT, for initial testing only)."
        )

    return host, {"Authorization": f"Bearer {access_token}"}


def run_statement(host, headers, sql, fiscal_year, period):
    warehouse_id = os.environ.get("DATABRICKS_WAREHOUSE_ID")
    if not warehouse_id:
        raise SystemExit("DATABRICKS_WAREHOUSE_ID is not set")

    payload = {
        "statement": sql,
        "warehouse_id": warehouse_id,
        "wait_timeout": "30s",
        "parameters": [
            {"name": "fiscal_year", "value": str(fiscal_year), "type": "INT"},
            {"name": "period", "value": str(period), "type": "INT"},
        ],
    }
    resp = requests.post(f"{host}/api/2.0/sql/statements", headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    result = resp.json()

    statement_id = result["statement_id"]
    deadline = time.time() + STATEMENT_TIMEOUT_SECONDS
    while result["status"]["state"] in ("PENDING", "RUNNING"):
        if time.time() > deadline:
            raise SystemExit(f"Databricks statement {statement_id} timed out after {STATEMENT_TIMEOUT_SECONDS}s")
        time.sleep(STATEMENT_POLL_INTERVAL_SECONDS)
        resp = requests.get(f"{host}/api/2.0/sql/statements/{statement_id}", headers=headers, timeout=30)
        resp.raise_for_status()
        result = resp.json()

    state = result["status"]["state"]
    if state != "SUCCEEDED":
        error = result["status"].get("error", {})
        raise SystemExit(f"Databricks statement {statement_id} failed ({state}): {error}")

    manifest = result["manifest"]
    if manifest.get("truncated"):
        # Mandatory rule #4: never trust a result without checking this flag.
        # A properly-scoped GROUP BY (mainaccount x ~16 entities) should never
        # hit the 12,288-row cap; if it does, the query needs the pagination
        # pattern from the project instructions before this script is safe to
        # rely on for a real close.
        raise SystemExit(
            "Databricks result was TRUNCATED (row cap hit). Refusing to "
            "produce a trial balance from a truncated result set -- add "
            "pagination to sql/consolidated_trial_balance.sql before rerunning."
        )

    columns = [c["name"] for c in manifest["schema"]["columns"]]
    rows = []
    chunk = result.get("result", {})
    rows.extend(chunk.get("data_array", []))

    # Follow any additional chunks (defensive; aggregated result sets here
    # are expected to fit in a single chunk).
    next_chunk_index = chunk.get("next_chunk_index")
    while next_chunk_index is not None:
        resp = requests.get(
            f"{host}/api/2.0/sql/statements/{statement_id}/result/chunks/{next_chunk_index}",
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        chunk = resp.json()
        rows.extend(chunk.get("data_array", []))
        next_chunk_index = chunk.get("next_chunk_index")

    return columns, rows


def build_report(columns, rows, entities):
    idx = {name: i for i, name in enumerate(columns)}
    entity_by_code = {e["code"]: e for e in entities}
    entity_codes = [e["code"] for e in entities]

    accounts = {}  # mainaccountid -> {name, byEntity: {code: {accounting, reporting}}}
    control_totals = {code: {"accounting": 0.0, "reporting": 0.0} for code in entity_codes}

    for row in rows:
        mainaccountid = row[idx["mainaccountid"]]
        mainaccountname = row[idx["mainaccountname"]]
        entity_code = row[idx["entity_code"]]
        accounting_amt = float(row[idx["accountingcurrencyamount"]] or 0)
        reporting_amt_raw = row[idx["reportingcurrencyamount"]]
        reporting_amt = float(reporting_amt_raw) if reporting_amt_raw is not None else None

        if entity_code not in entity_by_code:
            # Not one of the configured operating entities (e.g. a
            # consolidation ledger or DAT) -- excluded per entities.json.
            continue

        # Reporting-currency fallback for entities with no reporting
        # currency configured in D365 (HBBV, HBFM): use accounting-currency
        # amount, both are USD-denominated, per report owner's instruction.
        if reporting_amt is None and entity_by_code[entity_code].get("reportingCurrencyFallback"):
            reporting_amt = accounting_amt

        acc = accounts.setdefault(mainaccountid, {"mainAccountId": mainaccountid, "mainAccountName": mainaccountname, "byEntity": {}})
        acc["byEntity"][entity_code] = {"accounting": accounting_amt, "reporting": reporting_amt}

        control_totals[entity_code]["accounting"] += accounting_amt
        if reporting_amt is not None:
            control_totals[entity_code]["reporting"] += reporting_amt

    return {
        "accounts": sorted(accounts.values(), key=lambda a: a["mainAccountId"]),
        "entities": entities,
        "controlTotals": control_totals,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fiscal-year", type=int, required=True)
    parser.add_argument("--period", type=int, required=True, help="Fiscal period end, 1-12 (or per the entity's calendar)")
    parser.add_argument("--dry-run", action="store_true", help="Print the SQL and exit without calling Databricks")
    args = parser.parse_args()

    sql = load_sql()
    entities = load_entities()

    if args.dry_run:
        print(sql)
        print(f"\n-- parameters: fiscal_year={args.fiscal_year}, period={args.period}", file=sys.stderr)
        return

    host, headers = get_auth_header()
    columns, rows = run_statement(host, headers, sql, args.fiscal_year, args.period)
    report = build_report(columns, rows, entities)
    report["fiscalYear"] = args.fiscal_year
    report["period"] = args.period
    report["generatedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # Flag any entity whose control totals don't tie (per the project's
    # mandatory "use the balance check" working practice). A clean, complete
    # extract nets debits and credits to ~0.00 per entity.
    warnings = []
    for code, totals in report["controlTotals"].items():
        if abs(totals["accounting"]) > 0.01:
            warnings.append(f"{code}: accountingcurrencyamount does not net to zero ({totals['accounting']:.2f}) -- extract may be incomplete or filtered mid-voucher")
    report["warnings"] = warnings

    print(json.dumps(report))
    if warnings:
        print("\n".join(warnings), file=sys.stderr)


if __name__ == "__main__":
    main()
