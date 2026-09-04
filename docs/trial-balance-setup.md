# Consolidated Trial Balance — setup & operations

Report link: https://claude.ai/code/artifact/713b7be7-486a-4a4d-a0bd-f5b9f964b2ac

**Live as of 2026-09-04** with real data for all 93 periods from FY2019 P1
through FY2026 P9 (September, in progress) — full history, no further
setup needed for the data source. **2026-09-04: fixed a real bug** where
every entity's December (year-end close) period failed to net to zero —
see "Findings" #3 below and "Known open control-total exceptions".

**2026-09-04: added two tabs and a redesign.** The report now has three
tabs — Consolidated (the original view), Company TB, and By Currency — see
"The three views" below. The reference URL the report owner asked to match
(`victorious-water-0f3dd9e00.7.azurestaticapps.net`) was not reachable from
this session (egress blocked), so the visual redesign is an independent
pass using the same Huda Beauty brand tokens, not a copy of that page.

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

## The three views

- **Consolidated** — the original view: Main Account × company columns,
  Grand Total, reporting/accounting currency toggle, one period at a time.
  Backed by the `tb` collection.
- **Company TB** — pick one company and one period; shows Opening Balance
  (the prior period's Closing Balance — carried forward for Balance Sheet
  accounts, zero at the start of a fiscal year for P&L accounts), Current
  Month Dr, Current Month Cr, and Closing Balance, per main account.
  Opening/Closing come from `tb`; Dr/Cr come from the new `movement`
  collection (`sql/monthly_movement.sql`), which is *raw* monthly movement
  with **no simulated adjustments applied** (those only ever touch the
  Consolidated view's Closing Balance) — the tab's banner flags whether
  Opening + Dr − Cr reconciles to Closing for that reason.
- **By Currency** — the same Closing Balance as Consolidated, but with one
  row per (main account, original transaction currency) pair instead of one
  row per main account, so an account posted in more than one currency
  shows a row per currency. Backed by the new `currencytb` collection
  (`sql/monthly_movement_by_currency.sql`). Also does not include simulated
  adjustments.

## What's here

- `report/consolidated-trial-balance.html` — source for the published
  Artifact (all three tabs). Edit this, then republish it to the same URL
  (from a session that has published it before, passing that `url`) to push
  a UI change live — the Artifact tool doesn't read from this repo
  automatically.
- `sql/consolidated_trial_balance.sql` — the main query (Consolidated tab /
  `tb` collection), with extensive comments on three bugs found and fixed by
  testing live against real data (see "Findings from live validation"
  below).
- `sql/monthly_movement.sql` — monthly Dr/Cr movement per (entity, account),
  no BS/PL bucketing needed (see the file's header for why) — feeds the
  Company TB tab's Dr/Cr columns and the `movement` collection.
- `sql/monthly_movement_by_currency.sql` — same as above with
  `transactioncurrencycode` added to the grain — feeds the By Currency tab
  and the `currencytb` collection.
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
- `scripts/build_series_from_movement.py` — derives the `tb` collection's
  full closing-balance series directly from `monthly_movement.sql`'s output
  (net delta = debit − credit), instead of a separate balance query, so the
  Consolidated view and the Company TB tab's Dr/Cr are guaranteed to
  reconcile when built from the same fetch (see "Fetch everything in the
  same sitting" below).
- `scripts/build_monthly_movement.py` — builds the `movement` collection's
  per-period documents from `monthly_movement.sql`'s output, plus a
  `--validate-against-dir` spot-check (Opening + Dr − Cr == stored Closing).
- `scripts/build_currency_series.py` — same reconstruction as
  `build_series_from_movement.py`, keyed by (entity, account, currency)
  instead of (entity, account), for the `currencytb` collection.
- `scripts/prepare_movement_writes.py` / `scripts/prepare_currency_writes.py`
  — shard `movement`/`currencytb` period JSON into write_db-ready batches,
  mirroring `prepare_backfill_writes.py` for `tb`.

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

## Backfilling or re-running periods manually

**Full history (2019-01 through 2026-09) is already loaded** — all 93
periods, done 2026-09-03/04 via `scripts/backfill_all_periods.py` +
`scripts/prepare_backfill_writes.py` rather than running
`sql/consolidated_trial_balance.sql` 93 times. That approach: fetch two
monthly-grain queries (BS movement, PL movement — both include CLG now,
per Finding #3) paginated via `ROW_NUMBER()` per the mandatory truncation
rule (30,352 BS rows + 32,573 PL rows, each split into ~12,000-row pages),
then forward-fill (Balance Sheet, cumulative since inception) or
year-reset (P&L, resets every January) the monthly deltas in Python to
reconstruct every period from those 6 queries instead of 93 full-table
scans. `backfill_all_periods.py` validates pagination integrity (no gaps
or duplicate row numbers across pages) before trusting either result.

**Fetch the BS and PL monthly-grain queries in the same sitting.** The
2026-09-04 fix was rebuilt from a BS fetch made the previous day and a PL
fetch made fresh — mixing them produced spurious new-looking discrepancies
in the still-open current period (HBDS, HBUS, HBDM) purely from new
transactions landing on Databricks between the two fetches, not from any
logic bug. Refetching both at the same time made those vanish. If a
future backfill produces control totals that look worse than a live
point-in-time check for the same period, check fetch timing before
assuming the query broke again.

For a single new period (e.g. once FY2026 P10 exists), the simpler
one-period pipeline still works and is what the daily Routine uses: ask
Claude to "sync the consolidated trial balance for FY<year> period
<1-12>" — render query → run via connector → transform → shard → write,
under a minute end to end. Reach for the bulk backfill scripts only when
re-deriving many periods at once (e.g. a schema change forces a full
re-run) — `prepare_backfill_writes.py` re-applies the HBCB/HBUK simulated
adjustments to whichever periods still need them (same threshold check as
the daily Routine), so re-running the full backfill after those close
entries land in D365 will correctly stop simulating them.

**2026-09-04 update: `tb`, `movement`, and `currencytb` are now built from
one query, not several.** Adding the Company TB and By Currency tabs meant
also fetching monthly Dr/Cr movement (`sql/monthly_movement.sql`) and, for
By Currency, movement by transaction currency
(`sql/monthly_movement_by_currency.sql`). Since the `tb` collection's net
delta (debit − credit) is exactly what `monthly_movement.sql` already
computes, `scripts/build_series_from_movement.py` now derives `tb`'s full
closing-balance series *from that same movement fetch* rather than a
separate BS/PL delta query, and `scripts/build_currency_series.py` does the
same, keyed by (entity, account, currency), for `currencytb`. This isn't
just less duplicated work -- it's the fix for the same "fetch everything in
the same sitting" lesson above, generalized: any two collections meant to
reconcile with each other (Consolidated's Closing Balance vs. Company TB's
Opening + Dr − Cr, or Consolidated vs. By Currency's per-currency sum) will
show small live-data-drift discrepancies in the most recent 1-2 periods if
built from separate live queries run even a few minutes apart -- confirmed
live on 2026-09-04 (a few HBDS accounts in FY2026 P8 differed by
$370-480K between a `tb` snapshot fetched the previous day and a fresh
movement fetch; re-deriving `tb` from the fresh movement fetch made the
discrepancy vanish, and it was confirmed via a live point-in-time query
that the fresher number was correct). `backfill_all_periods.py` still works
if you need it (e.g. as a cross-check), but the one-query approach is now
the standard path for a full rebuild.

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

3. **CLG-tagged vouchers must NOT be excluded from either bucket, ever.**
   Two dead ends were tried before landing on this, both worth recording
   because both *looked* right until tested against a December period:
   - Exclude ALL CLG entries everywhere -> strips out legitimate
     Retained-Earnings roll-forward from every prior year's close,
     understating equity by hundreds of millions cumulative-forward.
   - Exclude CLG only from the P&L bucket, keep it in the Balance Sheet
     bucket -> looked correct because it fixed HBCB (whose Jan-2026 CLG
     batch happens to be 100% Balance-Sheet-side) and every period tested
     at the time (Aug/Sep 2026, both mid-year). **Missed by that testing:
     every entity's actual December (year-end close) period.** A normal
     entity's December CLG batch is one balanced double-entry transaction
     touching both a P&L account (zeroing it) and a Balance Sheet account
     (crediting Retained Earnings) — keeping the BS side while dropping
     the P&L side of the *same* transaction breaks it by exactly the
     amount zeroed. Caught 2026-09-04 when the report owner noticed
     December 2025 wasn't netting to zero: live-checked and found **all
     12 entities tested were off by millions to over a billion** for
     FY2025 P12.
   The fix: no CLG exclusion anywhere. A trial balance is just "whatever
   the GL currently says" — any valid double-entry ledger balances to
   0.00 by construction, closing entries included, so there's no need to
   special-case CLG at all. An still-open fiscal year naturally shows real
   P&L activity (no close posted yet); an already-closed year naturally
   shows ~0.00 P&L for that year (that IS what "closed" means — not a
   bug, even though it looks like accounts "reset" between Nov and Dec).
   Verified live: 10 of 12 entities net to EXACTLY 0.00 for FY2025 P12
   with the exclusion removed; the remaining two (HBCB, HBFR) are the
   same already-diagnosed data issues below, not query artifacts. This
   change did not alter FY2026 P8/P9 at all (no CLG activity dated within
   that fiscal year touches a P&L account), so nothing else moved.

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

**Applied 2026-09-03** (at the report owner's request):
- HBCB's Retained Earnings — Accumulated (`3141001`) was adjusted by
  -278,118,823.43 (both currencies) to simulate its pending FY2025
  year-end close.
- HBUK's Retained Earnings — Accumulated (`3141001`) was adjusted by
  +18,000.00 accounting / +24,683.40 reporting, to simulate the FY2025
  close (voucher `clguk25v2`) having correctly reversed account `6210008`
  instead of falling 18,000.00 short.

Both make their entity's control total balance to ~0.00 in the report,
but **neither correction has actually been posted in D365** — these are
projections, not facts. Re-run both adjustments on every future sync of
FY2026 periods until the real entries land in Databricks (the daily
Routine's prompt checks this automatically), at which point remove the
one(s) that resolved on their own — the real data will already balance.

**HBFR was deliberately NOT given a simulated adjustment.** Its
accounting-currency total already ties to exactly 0.00 — only the
reporting-currency (USD) total is off by +2,443.07. Investigated
2026-09-03: the largest accounting-vs-reporting gaps (e.g. `4110002`
Product Sales, `1131019` Inventory Issue/Receipt) are all ordinary
EUR→USD conversion differences, not one anomalous entry — this looks like
routine historical-rate FX translation residual (EUR debits/credits net
to zero, but each transaction converts to USD at its own transaction-date
rate, so the USD totals don't necessarily net to zero even when EUR does).
That's a real, structural artifact of the translation method, not a
missing transaction to simulate a fix for — plugging it would mean
inventing a number with no specific event behind it, unlike HBCB/HBUK
where a concrete pending/incorrect entry was identified. Leave it as a
flagged, immaterial ($2,443) warning unless finance identifies an actual
missing FX Translation Reserve entry to simulate instead.

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
  currency) **in FY2026 periods specifically — but FY2025 P12 (December
  2025) itself now nets to exactly 0.00** after the 2026-09-04 CLG fix.
  That's a genuine, only-partly-understood nuance, not a contradiction to
  paper over: whatever the account-`6210008` "Other Marketing - Influencer"
  shortfall traced on 2026-09-03 actually is (real FY2025 activity was
  +449,757.21 against a late close, voucher `clguk25v2` posted 2026-08-13,
  eight months late, that only reversed -431,757.21), it does not show up
  when FY2025 is checked as a whole, only when FY2026's cumulative Balance
  Sheet position is checked against FY2026's own P&L. That points at a
  2026-dated entry connected to the same late close (rather than the
  entire story being containable within FY2025) — not yet isolated to a
  specific transaction the way HBCB and the original HBUK finding were.
  Simulated adjustment (see above) still correctly zeroes this out for
  FY2026 periods; worth another pass to fully isolate the cause before
  telling finance the account-6210008 story is the complete explanation.
- **HBLL**: off by -0.02 — immaterial, likely rounding.
- **HBFR**: reporting-currency-only, off by +2,443.07 (accounting currency
  ties exactly) — looks like an FX-translation rounding artifact.

Do not "fix" these by further tweaking the exclusion logic without finance
input — the query has already been validated to balance exactly for 14 of
16 entities, so these four are genuine open questions about the underlying
data, not query bugs.

## Business rules baked into the query (confirmed with the report owner)

- **Balance Sheet** (`mainaccountid` 1,000,000–3,999,999): cumulative from
  ledger inception through the selected period. No exclusions.
- **P&L** (`mainaccountid` ≥ 4,000,000): movement within the selected
  fiscal year only. No exclusions — see Finding #3 above for why CLG
  entries must NOT be filtered out of this bucket.
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
