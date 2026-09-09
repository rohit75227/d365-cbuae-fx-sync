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
this session (egress blocked); the report owner later shared a screenshot
of it instead, and the header/nav/table-header styling was rebuilt to match
that (black masthead, "hudabeauty" wordmark, pink pill tabs, pink table
headers) on 2026-09-05.

**2026-09-05: the daily sync now updates all four collections, not just
`tb`.** See "Daily refresh" below for the corrected procedure — the
Routine's own prompt (written before Company TB / By Currency existed)
only ever touched `tb`, which would have left `movement`/`currencytb`/
`currencymovement` silently stale for the current period every day.

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

## The four views

- **Consolidated** — the original view: Main Account × company columns,
  Grand Total, reporting/accounting currency toggle, one period at a time.
  Backed by the `tb` collection.
- **Company TB** — pick one company (or "All Companies") and one period;
  shows Opening Balance (the prior period's Closing Balance — carried
  forward for Balance Sheet accounts, zero at the start of a fiscal year for
  P&L accounts), Current Month Dr, Current Month Cr, and Closing Balance,
  per main account. Opening/Closing come from `tb`; Dr/Cr come from the
  `movement` collection (`sql/monthly_movement.sql`), which is *raw* monthly
  movement with **no simulated adjustments applied** (those only ever touch
  the Consolidated view's Closing Balance) — the tab's banner flags whether
  Opening + Dr − Cr reconciles to Closing for that reason. A third currency
  option, **Transaction Currency** (added 2026-09-08), shows the RAW amount
  actually posted (`gjae.transactioncurrencyamount`, not converted to
  accounting or reporting currency) with one row per (account, company,
  transaction currency) — reuses `currencytb`/`currencymovement` (the same
  collections the By Currency tab already used), which now also carry a
  `transaction` field per cell alongside `accounting`/`reporting`. Totals
  are always shown in this mode even though summing different currencies
  together isn't a meaningful single number (explicit report-owner request:
  "TB will not be zero but it's fine") — each row's own Opening + Dr − Cr =
  Closing identity is still checked and still holds, it's only the
  cross-currency Grand Total that's non-meaningful.
- **By Currency** — same shape as Company TB (pick one company + one
  period): Opening Balance / Current Month Dr / Current Month Cr / Closing
  Balance, but with one row per (main account, original transaction
  currency) pair instead of one row per main account. Backed by
  `currencytb` (closing balances) and `currencymovement` (Dr/Cr), both from
  `sql/monthly_movement_by_currency.sql`. Also does not include simulated
  adjustments.
- **Intercompany Reconciliation** (added 2026-09-07, redesigned 2026-09-08
  twice — see the dated notes below) — one row per (Company, Offset
  Company) relationship, with a Company/Offset-Company filter (defaults to
  all companies) and an Account/Offset Account column showing which
  underlying main account(s) feed each side. As of the 2026-09-08 netting
  change: **Net Balance** is the Company's own receivable-from-Offset-Company
  account netted against its own payable-to-Offset-Company account (both
  from the Company's own books, if it holds both); **Offset Net Balance** is
  the same netting from the Offset Company's own books. Difference = Net
  Balance + Offset Net Balance — a nonzero difference flags a genuine
  intercompany imbalance (including one side booked without the other), not
  a data error. Kayali-counterparty accounts (a related but separate
  brand/legal group) and any account with a zero balance for the selected
  period are excluded server-side, before the data ever reaches the
  `intercompany` collection. Backed by `sql/intercompany_movement.sql` +
  `scripts/build_intercompany_periods.py` (see "What's here" below) — unlike
  the other three collections this one is built by forward-summing ONE
  fetch of full-history monthly movement rather than a per-period
  cumulative query, since the account universe is narrow enough (~80
  accounts, ~5,600 movement rows across all history as of 2026-09-07) to fit
  in a single un-paginated query.

**2026-09-08: Intercompany Reconciliation netted each side's own AR and AP
against the same counterparty, and deduped mirrored rows.** Report-owner
feedback: a company can hold BOTH a receivable-range and a payable-range
account against the very same counterparty (e.g. HBDM sold something to
HBFZ, creating HBDM's own AR-HBFZ, and separately owes HBFZ for something
else, creating HBDM's own AP-HBFZ) — the tab needs to net those together
per company, not show only the receivable side. Changed `arValue`/
`payableValue` (rendered as **Net Balance** / **Offset Net Balance**) to
each be that company's own AR-against-counterparty PLUS that same
company's own AP-against-counterparty (both from that one company's
books), for both the Company side and the Offset Company side. A side
effect worth knowing: before this change, a company pair where BOTH
companies each held their own AR account against the other produced TWO
directional rows (A→B and B→A) that showed genuinely different figures
(each row's "Accounts Receivable" was a different account). After netting,
those two rows become exact mirrors of each other (row A→B's Net Balance
equals row B→A's Offset Net Balance, and vice versa), so the redesign also
dedupes to ONE row per unordered company pair — when "All Companies" is
selected, the lower-entity-order code becomes "Company"; when filtered to
one company, that company is always shown as "Company" regardless of
entity order, so the filter still reliably lists everything that company
has a relationship with.

**2026-09-04, later same day: fixed Company TB / By Currency hanging on
"Connecting...".** Both tabs' one-shot reads used `.get()` with no error
handling, so any rejection failed silently with no visible feedback,
leaving the dropdowns empty forever. Both now read through a shared
`onSnapshot`-based one-shot helper (the same mechanism Consolidated was
already using successfully) with an explicit timeout and `.catch()` on
every chain, so a real failure now shows a message instead of hanging. By
Currency was also redesigned at this point to match Company TB's shape
(see above) instead of the original all-companies-as-columns layout, per
follow-up feedback. `scripts/build_currency_movement.py` /
`scripts/prepare_currency_movement_writes.py` build the `currencymovement`
collection from the already-fetched `monthly_movement_by_currency.sql`
pages (no new Databricks query needed) and were validated to reconcile
exactly with `currencytb`'s closing balances before pushing.

**2026-09-08: added a Transaction Currency view to Company TB.** Report-owner
request: "in the company tb tab can you add another button for transaction
currency, in this case the value should come from Transaction currency
amount column and currency should also come. In this case TB will not be
zero but its fine." Added `transactioncurrencyamount` to
`sql/monthly_movement_by_currency.sql` (summed into `debit_txn`/`credit_txn`),
carried through `build_currency_series.py` (new `transaction` field per
`currencytb` cell) and `build_currency_movement.py` (new
`debitTransaction`/`creditTransaction` fields per `currencymovement`
record), then backfilled across all 93 existing periods (2019-01 through
2026-09) so the new button works for every period the report already
covers, not just new ones going forward. The view reuses the existing
`currencytb`/`currencymovement` collections rather than creating new ones —
no new Databricks query was needed, just two more columns on the query
that already feeds By Currency. Per the explicit instruction above, the
Grand Total row is always shown even when it sums figures posted in
different currencies (unlike the accounting-currency/All-Companies view
elsewhere in the report, which suppresses a meaningless total) — each row
above it still reconciles correctly (Opening + Dr − Cr = Closing) since a
single row never mixes currencies, only the Grand Total does.

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
  and the `currencytb` collection. Also selects
  `transactioncurrencyamount` and sums it into `debit_txn`/`credit_txn`
  (added 2026-09-08) so `currencytb`/`currencymovement` can carry a native
  (unconverted) `transaction` value alongside the existing
  `accounting`/`reporting` ones, for Company TB's Transaction Currency
  view.
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
  instead of (entity, account), for the `currencytb` collection. Since
  2026-09-08 each `byEntity` cell also carries a `transaction` value (the
  cumulative native-currency amount, tracked with its own running total
  alongside `accounting`/`reporting` so a P&L year-reset resets all three
  together) sourced from `monthly_movement_by_currency.sql`'s
  `debit_txn`/`credit_txn`. `scripts/build_currency_movement.py` likewise
  adds `debitTransaction`/`creditTransaction` to each `currencymovement`
  record.
- `scripts/prepare_movement_writes.py` / `scripts/prepare_currency_writes.py`
  — shard `movement`/`currencytb` period JSON into write_db-ready batches,
  mirroring `prepare_backfill_writes.py` for `tb`.
- `sql/intercompany_movement.sql` — monthly Dr/Cr movement for the
  intercompany receivable (`1122001`-`1122999`) and payable
  (`2112001`-`2112999`) account ranges only, Kayali-named accounts already
  excluded (`LOWER(ma.name) NOT LIKE '%kayali%'`) — feeds the Intercompany
  Reconciliation tab.
- `scripts/build_intercompany_periods.py` — forward-sums that ONE query's
  full-history monthly movement into a per-period cumulative balance for
  every period from FY2019 P1 through the given `--latest-ym` (both account
  ranges are pure Balance Sheet, cumulative-since-inception, no P&L
  year-reset needed). Because the whole history is fetched fresh in one
  query rather than blended with an old stored baseline, this is NOT the
  "incremental build is unsound against backdating" trap described below —
  it's algebraically identical to a direct cumulative-to-date query at every
  period end, just far cheaper given the narrow account universe. Drops an
  account from a period's output entirely if every entity's balance is
  ~0.00 that period (report requirement: no zero-balance rows) — unlike
  `tb`, which keeps zero accounts so they don't disappear and reappear
  across periods.
- `scripts/prepare_intercompany_writes.py` — shards
  `build_intercompany_periods.py`'s per-period JSON into write_db-ready
  batches for the `intercompany` collection, mirroring
  `prepare_backfill_writes.py` for `tb`.

## Daily refresh

A Routine fires into this session daily at 04:00 UTC. As of 2026-09-05 the
connector is reachable from the Routine firing (the earlier "connectors
parameter not available for this org" API rejection is no longer blocking
it — confirmed by a live firing that ran the connector successfully).

**The Routine's own stored prompt is still the pre-Company-TB/By-Currency
version** (query → transform → shard → write for `tb` only) — update it via
`update_trigger` when convenient, but until then treat this doc as the
authoritative procedure, since the stored prompt would silently under-sync
otherwise. The correct daily procedure updates **all four collections**:

1. Determine fiscal year (= calendar year) and period (= calendar month)
   from today's date.
2. `python3 scripts/render_query.py --fiscal-year <FY> --period <P>`, run
   via `execute_sql_read_only`. If `manifest.truncated` is true, stop — the
   query needs `ROW_NUMBER()` pagination, don't guess a fix. Transform with
   `scripts/transform_connector_result.py <raw_file> --fiscal-year <FY>
   --period <P> > report.json`, then chain the HBCB/HBUK simulated
   adjustments (see the Routine's stored prompt or the "Simulated
   adjustments" section below for the exact commands), then
   `scripts/build_db_writes.py < report_final.json > writes.json` and write
   its batches to the `tb` collection (this part matches the original
   design and is correct as-is).
3. **Also refresh `movement`, `currencytb`, and `currencymovement` for the
   current period** — these do NOT self-update from step 2:
   - `sql/monthly_movement.sql` and `sql/monthly_movement_by_currency.sql`,
     scoped to just the current month (`{{RANGE_START}}` = first of this
     month, `{{RANGE_END_EXCLUSIVE}}` = first of next month — hand-substitute,
     `render_query.py` only handles `consolidated_trial_balance.sql`). A
     single month is small (a few hundred rows), one page suffices.
   - `scripts/build_monthly_movement.py` / `scripts/build_currency_movement.py`
     on that page → `scripts/prepare_movement_writes.py` /
     `scripts/prepare_currency_movement_writes.py` → write_db. Since
     2026-09-08 `sql/monthly_movement_by_currency.sql` also selects
     `transactioncurrencyamount`, so `currencytb`/`currencymovement` pick up
     the `transaction`/`debitTransaction`/`creditTransaction` fields
     automatically on every future sync — no separate step needed for
     Company TB's Transaction Currency view.
   - For `currencytb`, do **not** derive it incrementally from the prior
     period's stored value (see the backdating finding just below for why)
     — instead run a direct cumulative-by-currency query for the current
     period (same BS-cumulative/PL-FYTD WHERE clause as
     `consolidated_trial_balance.sql`, with `txn_ccy` added to the
     SELECT/GROUP BY, no separate SQL file for this yet — see the
     2026-09-05 sync in git history for the exact query used), transform,
     shard with `prepare_currency_writes.py`, write. Cross-check it against
     the same period's `tb` (sum `currencytb` across currency per account,
     compare to `tb`'s per-account value) — should match exactly except the
     entities with an active simulated adjustment (`tb` carries it,
     `currencytb` correctly never does).
4. Update `tb/index`: replace the entry for this period's key with a fresh
   `generatedAt`, keep every other entry, write back.
5. **Refresh `intercompany` for the current period** (added 2026-09-07,
   feeds the Intercompany Reconciliation tab): re-run
   `sql/intercompany_movement.sql` in full (no date range — it fetches
   every month of history in one un-paginated query, ~5,600 rows as of
   2026-09-07, comfortably under the 12,288-row cap) via
   `execute_sql_read_only`, then `python3
   scripts/build_intercompany_periods.py <raw_file> --out-dir <dir>
   --latest-ym <this period's YYYY-MM>` (this rebuilds every period
   2019-01 through the current one from scratch, not just the current
   period — cheap given the narrow account universe, and it means a
   backdated correction anywhere in intercompany's history self-corrects
   every sync without a separate spot-check), then
   `scripts/prepare_intercompany_writes.py` → write_db batches for every
   period whose `report_<key>.json` output actually changed (comparing
   against what's currently stored is optional but keeps the batch count
   down — writing every period unconditionally is also correct, just
   pricier). Cross-check the current period's intercompany accounts against
   `tb`'s own values for those same mainaccountids (sum should match
   exactly, since `intercompany` is a subset of `tb`'s account universe
   minus Kayali) before considering this step done.

**Connector response cell shape has changed since these scripts were
written, and can vary by call.** The claude-databricks-connector has been
observed returning two different per-cell JSON shapes across sessions —
older `result.data_array` with cells `{"string_value": ...}`, and (seen
2026-09-05) `result.data_typed_array` with cells `{"str": ...}` — and even
inline vs. saved-to-file responses from the *same* query can differ.
`transform_connector_result.py`, `build_monthly_movement.py`, and
`build_currency_movement.py` all handle both shapes now
(`cell_value()` checks `string_value` then `str`); if a future connector
version introduces a third shape, extend those `cell_value()` functions
rather than picking one shape and assuming it's universal.

**A backdated correction can make the prior period's stored closing stale
— check for this on every sync, don't assume "prior period is settled."**
Found live on 2026-09-05: HBUK/HBDS/HBDM had ~$1.5-50M of backdated
corrections (accounting date in August, but `createddatetime` after
2026-09-04's sync) land between two consecutive daily syncs — 73 (account,
entity) combinations were off by more than $1 when a fresh query for
August's own cutoff was compared against August's *already-published*
`tb`. This is not a query bug; it's normal GL activity (late-dated
corrections), but it means the "prior period" a sync treats as a fixed,
trustworthy baseline can silently drift. **Before trusting the current
period's Opening Balance (= prior period's stored Closing), spot-check it**:
re-run the prior period's own direct query and diff against what's
currently stored for a sample of accounts. If there's drift beyond
immaterial rounding, refresh the prior period's `tb`, `currencytb`,
`movement`, and `currencymovement` too (same procedure as steps 2-3 above,
substituting the prior period), or Company TB / By Currency will show a
"does not reconcile" banner for the current period that has nothing to do
with today's sync — it's yesterday's stored data being wrong, not today's.
Validate a fix by checking Opening (prior closing) + Dr − Cr = Closing
across every (account, entity) combination for the current period, not
just a sample, before considering the sync done (the file shapes are small
enough for this to be a cheap, ordinary Python check, not an approximation).

**2026-09-09 daily sync: backdating drift recurred on August, confirming
this needs checking every day, not just once.** FY2026 P9's sync found
August's already-published `tb` stale by up to $97.5M on one account
(`1122105`/HBFZ) — 132 of 1,726 (account, entity) combinations off by more
than $1, ~$259M total absolute drift, all ordinary late-dated GL activity
(same pattern as the 2026-09-05 finding above, recurring independently).
Refreshed August's `tb`, `currencytb`, `movement`, and `currencymovement`
alongside September's per the procedure above; validated Opening + Dr − Cr
= Closing across every (account, entity) combination for both periods
(1,726 and 1,727 combos respectively, zero mismatches beyond the three
active simulated-adjustment cells). Also noted while cross-checking
`currencytb` against `tb`: HBBV's `reportingCurrencyFallback` override is
applied unconditionally in `build_currency_series.py` (always substitutes
accounting for reporting) but only conditionally (only when reporting is
literally NULL) in `transform_connector_result.py` — a small (~$3,785),
pre-existing inconsistency between how `tb` and `currencytb` handle that
one entity's reporting-currency fallback, not something introduced by this
sync. Not fixed here (out of scope for a daily sync); worth reconciling
the two scripts' fallback logic in a future pass if it grows.

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

**HBFR: revisited and given a simulated adjustment on 2026-09-08.** The
2026-09-03 investigation (see the two paragraphs below, kept for history)
concluded this was a diffuse "historical-rate FX translation residual"
with no specific event to point at, and deliberately left it unsimulated.
A report viewer's artifact comment (anchored on the Consolidated tab's
Jan 2021 Grand Total, HBFR column) asked why the gap traces to "the HSBC
account," which prompted a closer look and found an actual concrete
cause, the same kind HBCB/HBUK already have:
- HBFR's accounting-currency (EUR) total ties to exactly 0.00 in every
  period, always. The entire reporting-currency (USD) gap comes from
  FY2020 P&L activity: `SUM(reportingcurrencyamount)` across every P&L
  account (`mainaccountid >= 4000000`) for HBFR's ledger, dated in
  calendar 2020, is exactly **-2,443.069** while the matching
  accounting-currency sum is exactly **0.00** — a perfect match to the
  gap the report has always shown for FY2021+ periods, confirming the
  entire gap is this one fiscal year's unclosed P&L, not a running
  translation residual.
- The largest single piece (+2,437.76 of the +2,443.07) is three lines on
  account `1112006` "HSBC - EUR account" — $0.00 EUR / nonzero USD each,
  dated 31-Dec-2020, voucher `HBFR-000001`, `createddatetime` 2022-01-26
  12:38 (a currency-revaluation entry for the bank account). The rest is
  smaller same-pattern entries on other
  accounts (vouchers `HBFR-ERAV-0000001..8`, `HBFR-EXV-0000001` /
  `HBFR-PAY-0000006`, plus `clgfr20v5`'s own residual).
- **Why it was never closed to Retained Earnings:** FY2020's closing
  voucher `clgfr20v5` was created 2022-01-25 10:46 — but `HBFR-000001`
  (the HSBC-EUR revaluation, and several of the smaller ones) was created
  **2022-01-26, a day after the close already ran.** The close couldn't
  sweep an entry that didn't exist yet. Confirmed by direct query: no
  `clg*`-tagged voucher for HBFR ledger touches this activity at all.

This is functionally the same story as HBUK's (a real entry that missed
its year-end close), not HBCB's kind of "close hasn't run yet" gap, so it
gets the same treatment: HBFR's Retained Earnings — Accumulated
(`3141001`) is now in `ENTITIES_TO_AUTO_SIMULATE`
(`scripts/prepare_backfill_writes.py`), so every period generated from
here on (and any future full backfill run via that script) picks it up
automatically, sized dynamically from that period's own raw HBFR total,
same as HBCB/HBUK.

**Backfilled 2026-09-08** across all 69 already-stored periods (2021-01
through 2026-09) at the report owner's explicit confirmation in chat
("fix the 2443 USD in jan 2021 balance... consider it as manual
adjustment and adjust it against the retained earnings"). For each
period: read the stored `tb` document + shard, summed HBFR's raw
`accounting`/`reporting` across every account row, and wrote the exact
negative of that sum into account `3141001`'s HBFR cell as a
`simulatedAdjustments` entry (same shape/format as HBCB/HBUK's), leaving
every other entity's data and adjustments untouched.

**Correction to the initial write-up above:** before running the
backfill, every period's raw HBFR gap was computed fresh from the live
stored data (not assumed) as a sanity check — and unlike the "compounds
year over year" prediction made when this was first investigated, the
actual raw gap turned out to be **essentially flat across all 69
periods**, consistently -2,443.06 to -2,443.07 in reporting currency
(accounting-side residual under $0.01 throughout) from 2021-01 all the
way to 2026-09. The per-account, per-year deltas found earlier via direct
Databricks queries on `1112006` alone (which *do* grow year over year)
turned out to be offset by other accounts' similar unswept-revaluation
activity in later years, keeping the entity-level total pinned near
$2,443 rather than compounding. The mechanism (computing each period's
adjustment dynamically from its own raw total, never a hardcoded figure)
was the right call regardless, since it's self-correcting if that ever
changes — it just happens to land on the same number every period in
practice.

One more thing this surfaced: the automatic "does not net to zero"
warning check only looks at the **accounting**-currency total per
entity (see the `HBFZ` example in `tb/2021-01`'s warnings) — a
reporting-currency-only gap like this one never trips it on its own.
The banner's control-total check should arguably check both currencies;
noted here rather than changed, since every entity with a known
reporting-currency gap is now covered by an explicit simulated
adjustment either way.

The two paragraphs below are the original 2026-09-03/09-04 investigation,
kept as-is for history; the "leave it as a flagged, immaterial ($2,443)
warning" conclusion in the first one is superseded by the above.

**Historical note (2026-09-03).** Investigated: the largest
accounting-vs-reporting gaps (e.g. `4110002` Product Sales, `1131019`
Inventory Issue/Receipt) are all ordinary EUR→USD conversion differences,
not one anomalous entry — this looked like routine historical-rate FX
translation residual (EUR debits/credits net to zero, but each
transaction converts to USD at its own transaction-date rate, so the USD
totals don't necessarily net to zero even when EUR does). Read at the
time as a structural artifact of the translation method, not a missing
transaction to simulate a fix for — plugging it would mean inventing a
number with no specific event behind it, unlike HBCB/HBUK where a
concrete pending/incorrect entry was identified.

**Historical note (2026-09-04, per report owner's ask to check why it
shows in Jan 2020).** Every other closed fiscal year for HBFR (2019,
2021-2025) nets to **exactly** 0.00 in both accounting (EUR) and
reporting (USD) currency. **Only FY2020** has a residual: EUR P&L nets to
exactly 0.00, but USD P&L nets to -2,443.07 — the entire gap lives in
this one year. January 2020 itself has zero activity (nothing originates
there specifically); the residual comes from real month-by-month FY2020
trading activity (Jun-Dec 2020) each converted at its own
transaction-date rate, plus a same-year closing/revaluation batch
(`clgfr20v5`, dated 2020-12-31 but not actually posted until 2022-01-25 —
over a year late) that includes lines with an EUR amount of exactly 0.00
but a nonzero USD amount (e.g. account `6810001` "Unrealised FX gains or
loss" and an `HBFR-FOR-0000010` foreign-currency revaluation batch, also
created 2022-01-25/24) — normal, EUR functional currency doesn't need a
matching entry for a USD-only translation adjustment. This correctly
narrowed the gap down to FY2020 specifically; the 2026-09-08 follow-up
above went one step further and identified the exact vouchers and the
sequencing bug (posted a day after the close) that explains why FY2020
was never actually closed out in reporting currency.

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

## HBUS: entire balance sheet nets to $0.00 as of Dec 2025 (real, not a bug)

**Report owner asked (2026-09-04) whether this was a mistake in how CLG
vouchers are handled.** It is not — traced live to a specific, real GL
posting:

- Every one of HBUS's ~66 non-zero Balance Sheet accounts as of Nov 2025
  (cash, AR, AP, inventory, provisions, tax, inter-unit balances — not just
  Retained Earnings) is **exactly** 0.00 as of Dec 2025. Verified per-account,
  not just in aggregate: zero accounts differ once the closing voucher below
  is included.
- Cause: journal `HBUS-GEN-2326441`, `subledgervoucher = 'clgus25v1'`
  (i.e. **CLG**, **US**, FY**25**), dated `accountingdate = 2025-12-31` but
  actually **created 2026-07-31** — posted about seven months late.
  14,729 lines, net **-7,801,838.26**, which exactly offsets HBUS's entire
  pre-existing cumulative Balance Sheet position (+7,801,838.26 from every
  other posting in HBUS's history) to zero. This is a full entity
  wind-down/closure entry, not an ordinary year-end "sweep P&L into Retained
  Earnings" close like other entities get (those only move Retained
  Earnings; this one zeroes AR, AP, inventory, cash, everything).
- This is correctly **included**, per Finding #3 above (no CLG exclusion
  anywhere) — excluding it would be the actual mistake, since it would show
  a stale, no-longer-true balance sheet for an entity whose books were
  closed. Confirmed by recomputing the same cumulative total with this one
  journal excluded: HBUS's "real" position reappears as +7,801,838.26 net.
- One data-quality curiosity spotted along the way, not requiring any query
  change: within that same voucher, account `1112011` (HSBC – CAD account)
  has only 6 lines but a **gross** (sum of absolute values) of ~113.5
  billion that nets to exactly 0.00 — some kind of technical offsetting
  pair with no economic effect. Harmless to the balance, but worth a
  finance/IT sanity check on why the closing batch generates lines of that
  magnitude.
- **Not yet confirmed with finance**: whether HBUS was deliberately wound
  down / liquidated / consolidated into another entity as of FY2025
  year-end. The report is accurately reflecting whatever was posted; it
  cannot confirm the business reason behind it.
- The report's own footer previously said "CLG year-end closing vouchers"
  were **excluded** — leftover text from before the 2026-09-04 fix, and the
  opposite of the query's actual (correct) behavior. Fixed the same day
  this was traced, since it's exactly the kind of wording that would make a
  viewer suspect this bug where none exists.

## Company TB / By Currency: Opening/Closing totals silently dropped zeroed accounts (real bug, fixed 2026-09-04)

**Report owner reported (screenshot)**: HBDS's Mar 2026 Opening Balance
Grand Total was `(142,377.96)` instead of ~0.00, and asked to double-check
the logic across all three tabs, all companies, all months, all
currencies — not just this one case.

**Root cause, traced and fixed same day**: `Company.render()` and
`Currency.render()` built their row/account list from
`Object.keys(closingByAccount)` (or `closingByKey`) — i.e. only accounts
present in the **current** period's `tb`/`currencytb` shard. Any account
that had a real, nonzero balance in the **prior** period but closes to
**exactly** zero in the current period naturally has no row in that
period's shard (the sync only stores nonzero balances) — so it silently
dropped out of the table entirely, along with its opening balance and any
movement that closed it out. The Grand Total was short by exactly the sum
of those dropped accounts' prior balances.

- Confirmed with live data: HBDS's stored `tb/2026-02` data (Feb 2026
  closing) independently ties to the Databricks ground truth exactly
  (verified via a live query: BS + FYTD P&L nets to 0.00, both accounting
  and reporting currency) — the **stored data was correct**; only the
  **rendering** dropped 3 accounts (`1142006`, `6210027`, `6790017`) that
  had a combined +142,377.96 reporting-currency balance in Feb 2026 but
  net to exactly zero in Mar 2026. That is the entire discrepancy,
  confirmed to the cent.
- **Fix**: both render functions now build their row set from the
  **union** of accounts (or account+currency keys) appearing in the
  closing data, the opening data, *and* the movement data — not closing
  data alone. An account that fully clears this period now still shows
  its correct Opening Balance, Dr/Cr, and a Closing Balance of 0.00, and
  is no longer dropped from the table or the Grand Total.
- **Validated against real production data** (not just synthetic test
  data) by running the actual page code in a headless DOM against the
  live `tb`/`movement`/`currencytb`/`currencymovement` documents for
  HBDS Mar 2026: Opening Grand Total now shows 0.00 (was `(142,377.96)`),
  Closing Grand Total shows 0.00, Dr and Cr both foot to 305,265,160.72,
  and Opening + Dr − Cr = Closing exactly, on **both** the Company TB and
  By Currency tabs (417 rows once split by currency vs. 177 by account).
  Cross-checked a second, unrelated entity/period (HBAQ, Jan 2026, the
  P&L-reset-at-period-1 special case) against live Databricks with the
  same result.
- **How widespread this was**: this class of bug affects *any* period
  where at least one account fully clears to zero relative to the prior
  period — normal, everyday activity (an account paid down to nil,
  year-end P&L resets, etc.), not a rare edge case. It is therefore likely
  this was visible on many company/period combinations across both
  affected tabs, exactly matching what the report owner observed. The fix
  is a general algorithmic correction (not period- or company-specific),
  so it applies uniformly everywhere once published — it does not require
  rebuilding any of the underlying `tb`/`movement`/`currencytb`/
  `currencymovement` data, since that data was already correct.
- **Consolidated tab is not affected**: it only ever shows one period's
  Closing Balance per entity (no Opening column, no cross-period
  reconciliation), so it has no equivalent bug to this one.
- **Broader due-diligence done in the same pass** (not exhaustive, but
  substantive): scanned every one of the 93 periods' self-reported
  control-total warnings — found nothing beyond the already-documented
  HBCB/HBUK simulated adjustments and immaterial ~$0.01 rounding noise on
  HBDM/HBFZ across a handful of periods (not a new finding, not
  actionable). Cross-checked `tb` vs `currencytb` for HBDS Mar 2026
  (1,208 account/entity combinations): only the two expected differences
  where `tb` carries the HBCB/HBUK simulated adjustment and `currencytb`
  correctly does not (per its own footer note), plus sub-cent floating
  point noise on ~127 keys — nothing material or unexplained.

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
