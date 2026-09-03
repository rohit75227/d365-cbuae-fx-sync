# Consolidated Trial Balance — setup & operations

Report link: https://claude.ai/code/artifact/713b7be7-486a-4a4d-a0bd-f5b9f964b2ac

The report reads a shared, org-internal database attached to that Artifact
(never Databricks directly — a browser page cannot reach Databricks safely).
A daily job populates that database from `hb_catalog.db_bronze_d365` using
the logic from the "GL Reporting from D365 Bronze Layer" Claude Project.
Until that job has run once, the report shows a "waiting for first sync"
state rather than any figures.

## What's here

- `sql/consolidated_trial_balance.sql` — the Databricks SQL query. Applies
  the four mandatory rules from the GL Reporting project (IsDelete
  COALESCE, uppercase entity comparison, CLG exclusion, truncation check),
  plus the fiscal-year/period and Balance-Sheet-vs-P&L logic agreed with
  the report owner (see "Business rules" below).
- `scripts/entities.json` — the 16 operating legal entities in scope
  (every `KY*` entity, the consolidation ledgers CHBD/CHBI/CHBU, and the
  shared `DAT` company are excluded — confirm this is correct before go-live).
- `scripts/sync_trial_balance.py` — calls Databricks (SQL Statement
  Execution API), runs the query for one fiscal year/period, and prints a
  JSON report to stdout. Talks only to Databricks; knows nothing about the
  Artifact.
- `scripts/build_db_writes.py` — takes that JSON on stdin and produces the
  `write_db` batch payloads (sharded to stay under the 256 KiB per-document
  limit), plus an `indexUpsert` note. Has no Artifact access either — it
  just prepares the payloads for whoever does.

## One-time setup you need to do

1. **Create a Databricks service principal**, scoped read-only to
   `hb_catalog.db_bronze_d365` (least privilege — it should not be able to
   read or write anything outside that schema):
   - Databricks workspace → Settings → Identity and access → Service
     principals → Add service principal.
   - Grant it `USE CATALOG` on `hb_catalog`, `USE SCHEMA` + `SELECT` on
     `db_bronze_d365` (or the specific tables: `generaljournalaccountentry`,
     `generaljournalentry`, `mainaccount`).
   - Grant it `CAN USE` on the SQL warehouse the sync should run against.
   - Generate an OAuth secret for it (Service principal → Secrets → Generate
     secret). Note the **Application ID** and the **secret**.
2. **Set these as environment variables on the Claude Code Environment**
   this session runs in (Environment settings in claude.ai/code — never in
   this repo, never pasted into chat):
   - `DATABRICKS_HOST` — e.g. `https://hudabeauty.cloud.databricks.com`
   - `DATABRICKS_WAREHOUSE_ID` — the SQL warehouse's ID (Warehouse →
     Connection details tab)
   - `DATABRICKS_CLIENT_ID` — the service principal's Application ID
   - `DATABRICKS_CLIENT_SECRET` — the OAuth secret generated above
3. Tell Claude once these are set — the daily Routine (already created,
   see below) will start succeeding on its next firing.

## Daily refresh

A Routine fires into this session once a day. On each firing, Claude:
1. Runs `python3 scripts/sync_trial_balance.py --fiscal-year <current FY>
   --period <current period>`.
2. Pipes that JSON through `scripts/build_db_writes.py`.
3. Calls the Artifact tool's `write_db` (`db_op: "batch"`) once per batch
   against the report's URL above, then updates `tb/index` by reading it
   first and merging in the new period (never blind-overwriting it, so
   previously synced periods stay browsable).
4. If `sync_trial_balance.py` reports control-total warnings (an entity's
   accounting-currency amount doesn't net to ~0.00), those are stored in
   the period document and shown as a banner on the report — they are not
   swallowed silently.

Only the current fiscal year/period is synced by default, so the report's
period selector will show one option until more periods are backfilled.

## Backfilling historical periods

Run the same two-script pipeline with a different `--fiscal-year`/`--period`,
then write its output the same way. Each period is independent and additive
— syncing 2026 P5 does not touch 2026 P6's data.

## Business rules baked into the query (confirmed with the report owner)

- **Balance Sheet** (`mainaccountid` 1,000,000–3,999,999): cumulative from
  ledger inception through the selected period.
- **P&L** (`mainaccountid` ≥ 4,000,000): movement within the selected
  fiscal year only, using `fiscalcalendaryear`/`fiscalcalendarperiod`
  (not calendar-date math).
- **Reporting currency (default view)**: `reportingcurrencyamount`, with
  HBBV and HBFM falling back to `accountingcurrencyamount` since neither
  has a reporting currency configured in D365 (both are USD-denominated).
- **Accounting currency view**: `accountingcurrencyamount` per company in
  its own local currency; the grand total is hidden in this view since
  summing AED + USD + GBP + EUR + SGD would be meaningless.
- **Excluded**: any entity whose code contains "KY"; CLG year-end closing
  vouchers (`subledgervoucher LIKE '%clg%'`, case-insensitive); soft-deleted
  rows (`IsDelete` is NULL-typed in the source, not `false`, per the GL
  Reporting project's mandatory rule).
- **Not included in scope, flag if this is wrong**: consolidation ledgers
  (CHBD, CHBI, CHBU) and the shared `DAT` company — these aren't in
  `scripts/entities.json` because they don't represent real operating
  companies for a trial balance, but this was an assumption, not something
  explicitly confirmed.

## Sharing the report

The report database makes the Artifact **organization-internal**: every
reader and writer must be a signed-in member of the Huda Beauty Claude
organization — it cannot be made public. Share it with the finance team
from the Artifact's share menu; anyone you share it with can open the same
link at any time and always sees the latest synced data, live (the page
subscribes to the database, so it updates in place — no reload needed).
Page writes are locked to admin-level sharing, so a viewer opening the
report cannot alter the figures from their browser.
