# Consolidated Trial Balance — setup & operations

Report link: https://claude.ai/code/artifact/713b7be7-486a-4a4d-a0bd-f5b9f964b2ac

**Live as of 2026-09-03** with real data for FY2026 periods 8 (August, complete)
and 9 (September, in progress) — no further setup needed for the data source.

## How data gets in (no credentials needed)

The report reads a shared, org-internal database attached to that Artifact
(a browser page can't reach Databricks directly). Behind that, this session
has the `claude-databricks-connector` — an org-level, pre-authorized MCP
connector (`mcp__claude-databricks-connector__execute_sql_read_only` /
`poll_sql_result`) — so **no service principal, no API token, no environment
variables are required.** If you see documentation elsewhere in this repo's
history describing a service-principal / REST API approach, that was the
original plan before the connector turned out to already be available —
it's been replaced.

## What's here

- `report/consolidated-trial-balance.html` — source for the published
  Artifact. Edit this, then republish it to the same URL (from a session
  that has published it before, passing that `url`) to push a UI change
  live — the Artifact tool doesn't read from this repo automatically.
- `sql/consolidated_trial_balance.sql` — the query, with extensive comments
  on three bugs found and fixed by testing live against real data (see
  "Findings from live validation" below).
- `scripts/entities.json` — the 16 operating legal entities in scope, with
  their ledger RECID, accounting currency, and reporting currency.
- `scripts/render_query.py` — substitutes the period-end/fiscal-year-start
  tokens in the SQL file with literal `TIMESTAMP` values (the connector
  takes a raw SQL string, no bind parameters) and prints the finished query.
- `scripts/transform_connector_result.py` — parses a saved
  `execute_sql_read_only` result file into the report JSON shape (accounts,
  entities, control totals, warnings).
- `scripts/build_db_writes.py` — shards that JSON into `write_db`-ready
  batches, staying under the 256 KiB per-document limit.

## Daily refresh — one thing left to fix

A Routine fires into this session daily at 04:00 UTC and follows the steps
in its own prompt (query → transform → shard → write). **However: this
platform rejected attaching the Databricks connector to a Routine via the
API** ("the connectors parameter is not available for this organization").
That means tomorrow's automatic firing will very likely run *without*
connector access and do nothing (its prompt tells it to leave a note rather
than fail silently). **To fix this, enable the connector for this Routine
from the claude.ai Routines UI** (Settings → Routines → "Daily consolidated
trial balance sync" → connector access) if that control exists for your
org; otherwise the report will need a manual re-sync each day — ask Claude
to "sync the trial balance for the current period" and it can do so
immediately, live, in under a minute.

## Backfilling or re-running a period manually

Ask Claude directly (in this session or a new one with the same repo and
connector access): "sync the consolidated trial balance for FY<year>
period <1-12>". The whole pipeline (render query → run via connector →
transform → shard → write to the report's database) took well under a
few minutes end to end when validated live.

## Findings from live validation (2026-09-03)

Three things the original project instructions didn't cover, found by
testing against real data before trusting any output — each would have
produced a **silently wrong, not obviously wrong** trial balance:

1. **`gje.fiscalcalendaryear` / `gje.fiscalcalendarperiod` are RECIDs, not
   literal years.** Values look like `5637148326`. There's no fiscal
   calendar reference table in this bronze schema to resolve them. Fixed
   by filtering on `gje.accountingdate` (TIMESTAMP, half-open ranges)
   instead — which is also what the project's own worked CLG example
   actually does, despite listing the other two columns as available.

2. **`gje.subledgervoucherdataareaid` is NULL for any GL entry not tied to
   a subledger voucher** — a large share of real postings (accruals,
   manual journals, intercompany, allocations). Using it to attribute
   entity/company silently dropped those rows, breaking every entity's
   debit=credit control total by hundreds of millions. Fixed by switching
   to `gje.ledger` (a RECID, populated on every row — verified: exactly 24
   distinct values across all of history, all mapping cleanly to the 16
   operating entities + 9 `KY*` entities + 8 stray NULL-ledger rows, with
   nothing left unexplained).

3. **CLG-tagged vouchers aren't purely a "zero out this year's P&L"
   artifact** — the batch that closes fiscal year N is split across a
   December-of-year-N posting and a January-of-year-(N+1) posting, and the
   January posting also carries the *Balance Sheet*-side retained-earnings
   movement. Excluding all CLG entries from the Balance Sheet bucket (as
   originally planned) dropped a real one-sided Retained Earnings movement
   with nothing to offset it. Fixed by excluding CLG-tagged entries **only**
   from the P&L bucket, never the Balance Sheet bucket. This alone fixed 14
   of 16 entities to net to exactly 0.00 debits=credits.

## Simulated adjustments (pro-forma, not posted in D365)

`scripts/apply_simulated_adjustments.py` lets a report viewer see the
trial balance "as if" a known-pending D365 entry had already been posted
— without ever touching the SQL query or blending a made-up number silently
into real GL data. Every use is recorded in the period document's
`simulatedAdjustments` array; the report renders those cells with a
dashed/diagonal pattern and a `†` marker (hover for the reason), and the
warning banner splits into a real "control-total check" section and a
separate "includes simulated, not-yet-posted adjustments" section — never
merged into one so a viewer can't mistake a simulated figure for a posted
one.

**Applied 2026-09-03** (at the report owner's request): HBCB's Retained
Earnings — Accumulated (`3141001`) was adjusted by -278,118,823.43 (both
accounting and reporting currency) to simulate its pending FY2025
year-end close. This makes HBCB's control total balance to ~0.00 in the
report, but **the actual close has not been posted in D365** — this is a
projection, not a fact. Re-run this adjustment on every future sync of
FY2026 periods until the real closing entry lands in Databricks, at which
point remove it (the real data will already balance on its own).

## Known open control-total exceptions

Surfaced as a warning banner on the report itself, not hidden:

- **HBCB**: off by +278,118,823.43 (AED). **Confirmed cause (per report
  owner): HBCB's FY2025 year-end close hasn't been run yet.** Verified in
  the data: HBCB's full, unrestricted ledger (every account, every date,
  no fiscal-year scoping) nets to ~0.00 — nothing is missing from
  Databricks — but HBCB's CLG-tagged closing entries for Jan-2025 and
  Jan-2026 touch only Balance Sheet accounts, never P&L, unlike every
  other entity. That means HBCB's 2024/2025 P&L (e.g. `4140003`
  Intercompany Dividend Income, cumulative -339,012,573.21 spanning
  Dec 2024-Jul 2026) was never transferred into Retained Earnings. Our
  query correctly excludes prior-year P&L from the current-year view, but
  since it was also never rolled into equity, it just disappears from the
  report — hence the gap. **This should self-resolve on its own** once
  finance posts HBCB's FY2025 close in D365 (no query change needed) —
  worth confirming it clears on the next sync after that happens, rather
  than assuming it's fixed.
- **HBUK**: off by -18,000.00 (accounting currency) / -24,683.40 (reporting
  currency). **Traced to a specific cause**, though not fully explained:
  HBUK's FY2025 year-end close (voucher `clguk25v2`, dated 2025-12-31) was
  actually posted on **2026-08-13** — eight months late. On account
  `6210008` "Other Marketing - Influencer", real FY2025 activity was
  +449,757.21 but the late close only reversed -431,757.21 — short by
  exactly 18,000.00. Every other account and every other year closes
  perfectly. Likely a marketing accrual posted to that account after the
  close figures were calculated, or a manual adjustment that didn't carry
  into the final reversal — worth asking whoever ran HBUK's FY2025 close
  in August 2026. Not visible from GL data alone why the close itself ran
  so late or what exactly caused the shortfall.
- **HBLL**: off by -0.02 — immaterial, likely rounding.
- **HBFR**: reporting-currency-only, off by +2,443.07 (accounting currency
  ties exactly) — looks like an FX-translation rounding artifact.

Do not "fix" these by further tweaking the exclusion logic without finance
input — the query has already been validated to balance exactly for 14 of
16 entities, so these four are genuine open questions about the underlying
data, not query bugs.

## Business rules baked into the query (confirmed with the report owner)

- **Balance Sheet** (`mainaccountid` 1,000,000–3,999,999): cumulative from
  ledger inception through the selected period, CLG entries included (they
  carry the real retained-earnings movement).
- **P&L** (`mainaccountid` ≥ 4,000,000): movement within the selected
  fiscal year only, CLG entries excluded (that's the mechanism that zeros
  P&L at close).
- **Reporting currency (default view)**: `reportingcurrencyamount`, with
  HBBV and HBFM falling back to `accountingcurrencyamount` since neither
  has a reporting currency configured in D365 (both are USD-denominated,
  though both currently have zero GL activity anyway).
- **Accounting currency view**: `accountingcurrencyamount` per company in
  its own local currency; the grand total is hidden in this view since
  summing AED + USD + GBP + EUR + SGD would be meaningless.
- **Excluded**: every `KY*` entity, the shared `DAT` company, and the
  consolidation ledgers CHBD/CHBI/CHBU — verified these have had **zero**
  GL activity in this bronze schema across all of history, so excluding
  them cost nothing in practice, not just in theory.

## Sharing the report

The report database makes the Artifact **organization-internal**: every
reader and writer must be a signed-in member of the Huda Beauty Claude
organization — it cannot be made public. Share it with the finance team
from the Artifact's share menu; anyone you share it with sees the latest
synced data live (the page subscribes to the database — no reload needed).
Page writes are locked to admin-level sharing, so a viewer opening the
report cannot alter the figures from their browser.
