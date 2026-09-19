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

**2026-09-14: UI enhancements — multi-select Main Account, sortable amount
columns, Company TB date range.** Report-owner requests, all client-side
(no new collections, no sync changes):
- The "Main Account" filter on Consolidated, Company TB, By Currency, and
  Intercompany is now multi-select (checkboxes in the same search-combo
  panel) instead of picking one account at a time; an empty selection
  still means "all accounts." A "Clear" button (Excel-filter-style,
  disabled when nothing is selected) is pinned above the checkbox list so
  it stays reachable without scrolling, added the same day per report-owner
  follow-up request.
- Every amount column, on all six tabs, is now sortable (click a header to
  sort highest-to-lowest, click again for lowest-to-highest).
- Company TB's Period dropdown was replaced with Start Date / End Date
  pickers (native `<input type="date">`, calendar icon restored — an
  earlier `appearance:none` had hidden it — and clicking anywhere in the
  field, not just the tiny icon, opens the calendar via `showPicker()`
  where the browser supports it; typing the date directly still works
  either way). Opening Balance is now the closing balance as of the day before
  Start Date, Closing Balance is as of End Date, and the old "Current
  Month Dr/Cr" columns are renamed "Current Period Dr/Cr" and sum every
  month's movement from Start Date through End Date inclusive. Both dates
  snap to the month they fall in — `tb`/`movement`/`currencytb`/
  `currencymovement` are only synced at month-end, so there's no daily
  granularity to interpolate. Applies to both the Reporting/Accounting
  mode and the Transaction Currency mode. The other tabs (By Currency,
  Intercompany, Vendor Balance, Customer Balance) are unchanged and still
  use a single period/month picker.

**2026-09-16: masthead logo, and a note on the Company TB date pickers.**
Report-owner request: replaced the plain text "hudabeauty" wordmark in the
masthead with the actual Huda Beauty logo image (copied from another
report artifact's `<img class="hb-logo">`, embedded here as a data URI so
no external asset load is needed; rendered white via `filter:brightness(0)
invert(1)` against the dark masthead background). Client-side only, no
sync changes. Separately: the Company TB Start Date / End Date fields now
open a full in-page calendar (month/year dropdowns, out-of-range days
disabled) instead of relying on the browser's native `showPicker()` --
the 2026-09-14 entry above described the `showPicker()` approach, which
has since been superseded in the live artifact.

**2026-09-16, later same day: Period dropdown now matches the Main
Account dropdown's style.** Report-owner request. The plain native
`<select>` used for Period on Consolidated, By Currency, Intercompany,
Vendor Balance, and Customer Balance is replaced with the same
search-combo shell as the "Main Account" filter (`.acct-combo`: a text
input opening a custom `.acct-combo-panel` list) via a new shared
`createPeriodCombo()` helper -- visually and behaviorally identical to
Main Account's `createAccountCombo()`, just without an "All" option and
keeping periods in the newest-first order `tb/index` already provides
instead of alphabetizing. Company TB is unaffected (it uses Start/End
date pickers, not a Period dropdown, since the 2026-09-14 change).

**2026-09-16, later still: fixed uneven control-box widths in the controls
bar.** Report-owner reported the Period box crowding out the Main Account
box (its text truncating) once Period held a real selected value. Root
cause: `.control-group` (the wrapper around each eyebrow + control) had no
explicit `flex-shrink`, so once the controls bar ran short on horizontal
space it shrank whichever box happened to yield first, unevenly, instead
of wrapping. Fixed by adding `flex:none` to `.control-group` so every
control box (Currency toggle, Period, Main Account, Export button, status
pill) keeps its natural width and the row wraps to a new line under space
pressure instead of squeezing any one box.

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

**2026-09-09: added a Main Account filter to all four tabs.** Report-owner
request: "add mainaccount filter as well in all the tabs... if select a
main account then table should get filter for that account." Each tab now
has a "Main Account" filter, rebuilt on every render from whatever accounts
are actually present in that render's own data (never a fixed roster), so
a previously selected account that isn't present after a
period/company/currency switch falls back to "All Accounts" instead of
silently filtering to nothing. Consolidated and By Currency filter their
row list directly by `mainAccountId`; Company TB filters by the account
segment of its `account|company` (or `account|company|txnCurrency` in
Transaction Currency mode) row keys, and the filter persists correctly
across a currency-mode switch since both `render()` and
`renderTransaction()` share the same `state.account` and filter widget.
Intercompany has no single `mainAccountId` per row (each row nets one or
two accounts per side), so it filters on whether the selected account is
among that row's own `arAccountIds`/`apAccountIds` (either side, either
company) rather than an exact match. Grand Totals recompute from the
filtered row set, same as any other filter in this report (e.g. Company
TB's per-company view) — a filtered total is that account's total, not an
error.

**2026-09-09, later same day: Main Account filter became a searchable
combo box, and warning banners became collapsible.** Report-owner
feedback: "In the main account dropdown can we have search also... Also,
The warning message which appears can we close it and if users wants to
check then they will click on details." The Main Account filter's plain
`<select>` (hundreds of accounts, hard to scroll through) was replaced
with `createAccountCombo()` — a text input backed by a custom dropdown
panel: click to browse the full list, type to filter by account ID or name
substring, click or Enter to select. All four tabs' filters share this one
helper, keeping the exact same `.populate(accountMap, currentValue)` /
resolved-value contract the old `populateAccountSelect()` had, so no
render-side filtering logic needed to change. Separately, every
`.banner` (control totals, simulated adjustments, reconciliation
notes, accounting-currency-view notices) now renders through a shared
`renderBanners()` helper: each banner shows a short one-line summary plus
a close (&times;) button, with any longer explanatory text collapsed
behind a "Details" toggle instead of always shown inline — a dismissed
banner reappears on the next data reload since it reflects live data, not
a one-time notice.

**2026-09-09, later still: fixed a controls-bar alignment bug, and added a
transaction-currency breakdown to Intercompany.** Report-owner feedback:
"See export to excel button is not in line with the columns it is little
off" — `.controls` used `align-items:center`, which vertically centered
the lone Export button and status text against the *whole* row height,
while every labeled dropdown (pushed down by its "eyebrow" label) sat
lower — so the button visibly floated above the others' baseline. Changed
to `align-items:flex-end` so every control shares the same bottom edge;
also gave the status text a bordered pill/chip treatment, a soft shadow +
hover lift to the Export button, and hover/active-state polish on
selects, the account-search input, and the segmented toggle. Verified with
a real headless-Chromium screenshot (Playwright, `/opt/pw-browsers/chromium`)
before publishing, not just by reading the CSS.

Separately, added a **Details** toggle button to the Intercompany tab
(report-owner: "if I click on [a Net Balance] I can get the value in
transaction currency and transaction currency code... add a button at top
which says details and then the currencycode and amount should come
underneath each value"). Clicking it fetches the SAME `currencytb`
collection Company TB's Transaction Currency mode already reads (no new
Databricks query) and, for each row, breaks Net Balance / Offset Net
Balance down by the transaction currency actually posted, summed across
that side's `arAccountIds`/`apAccountIds` (a side can span two accounts,
e.g. a company's own AR + AP against the same counterparty) exactly the
same way the main net figure is computed — the per-currency lines were
verified to sum back to the exact displayed Net Balance in a live-shaped
test. Independent of the Reporting/Accounting toggle, since transaction
amounts are a third, unconverted currency dimension.

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
  Company TB tab's Dr/Cr columns and the `movement` collection. **Still used
  as-is for `movement`/`currencytb`/`currencymovement`** — see the
  Closing/Opening-period finding below for the known gap this leaves on
  December (and slightly January) periods.
- `sql/monthly_movement_v2.sql` — supersedes `monthly_movement.sql` as the
  source for the `tb` collection only (2026-09-09): same shape and grain,
  but generically detects and correctly reclassifies D365's hidden
  "Closing"/"Opening" fiscal periods (shift Balance Sheet rows to next
  January, drop P&L rows) instead of merging them into the calendar month
  they happen to share a date with — see the dated finding below for full
  detail. Not yet used for `movement`/`currencytb`/`currencymovement`.
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
- `sql/vendor_balance.sql` / `sql/customer_balance.sql` — monthly Dr/Cr
  movement per (legal entity, vendor/customer account, month), from
  `vendtrans`/`vendtable` and `custtrans`/`custtable` joined to
  `dirpartytable` for the party name. Feeds the Vendor Balance / Customer
  Balance tabs. **`vendor_balance.sql` joins `vendtable` case-insensitively
  on `dataareaid`** (`LOWER(vd.dataareaid) = vt.dataareaid`) —
  `vendtrans.dataareaid` is always lowercase but `vendtable.dataareaid` is
  stored mixed-case (e.g. `"HBDS"`) for a large share of vendor master
  records, and an exact-match join silently drops every transaction for
  those vendors (found 2026-09-11: 115 of 262 Sept-2026 vendor rows were
  missing before this fix). `customer_balance.sql` does NOT need this fix
  — confirmed `custtable`/`custtrans` `dataareaid` casing matches exactly
  (0 unmatched rows either way).
- `sql/vendor_balance_by_currency.sql` / `sql/customer_balance_by_currency.sql`
  — same grain plus the original transaction currency (`amountcur`/
  `currencycode`), for each tab's Transaction Currency mode.
- `scripts/build_party_balance_periods.py` — generic `--kind
  {vendor,customer} --grain {balance,currency}` script, same forward-sum
  pattern as `build_intercompany_periods.py` (both vendor/customer
  balances are pure Balance Sheet / AP-AR, cumulative since ledger
  inception, no fiscal-year reset): one full-history query, forward-summed
  client-side into a per-period cumulative balance, zero-balance rows
  (`abs(balance) <= 0.01`) dropped per period.
- `scripts/prepare_party_balance_writes.py` — shards
  `build_party_balance_periods.py`'s per-period JSON into write_db-ready
  batches for the `vendor`/`customer` collections, mirroring
  `prepare_intercompany_writes.py`. Since balance and currency grains are
  built as separate passes but write into the SAME period document
  (`shardCount` from one, `currencyShardCount` from the other), it reads
  back the existing period file (if present) and merges rather than
  overwriting, so run order between the two grains doesn't matter.

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

**2026-09-10 daily sync: backdating drift recurred again on August (third
consecutive day), plus the first `intercompany` backdating check since it
was added.** FY2026 P9's sync found August's already-published `tb` stale
by 158 of 1,729 (account, entity) combinations (>$1 each), ~$628M total
absolute drift — same recurring pattern as 2026-09-05 and 2026-09-09, not
a new issue. Refreshed August's and September's `tb`, `movement`,
`currencytb`, and `currencymovement` per the procedure above; cross-checked
`currencytb` against `tb` (2 expected mismatches per period, both the
active HBUK/HBCB simulated Retained Earnings adjustment, exactly as
documented). Also ran the `intercompany` backdating check for the first
time on a routine sync (previously only spot-checked at initial rollout):
found the current period's stored data stale too (`2112105`/HBFZ off by
~$97.3M, `1122001`/HBFZ missing $141.5M entirely, among others) — rebuilt
all 93 `intercompany` periods from a fresh full-history query (cheap given
the narrow ~80-account universe, and self-corrects any backdated period
without a separate spot-check per period) and pushed all of them rather
than diffing each one first. Cross-checked against `tb` for both periods
(149 combos each, zero mismatches) and validated Opening + Dr − Cr =
Closing for September against August's freshly-refreshed opening (358
combos, zero failures) and for August against July's opening (760 combos,
only the same 3 pre-existing HBBV reporting-currency-fallback cells
failing, already documented above — not new). Confirms the backdating
check belongs in every field this sync touches, not just `tb`, since
`intercompany` draws from the same underlying GL activity and drifts for
the same reason.

**2026-09-10, later same day: full-history refresh requested after new FY2025
postings ("we have posted entries in 2025... make sure data is refreshed
for 2025 as well").** Rather than re-run the single-period daily pipeline,
re-fetched `sql/monthly_movement.sql`, `sql/monthly_movement_by_currency.sql`,
and `sql/monthly_movement_v2.sql` fresh across the FULL history (2019-01
through 2026-09, paginated) and rebuilt all 93 periods of `tb`, `movement`,
`currencytb`, and `currencymovement` from scratch, plus `intercompany` (its
existing full-rebuild-every-time design already covers this).

- **Mistake caught before publishing**: the first pass built `tb` from the
  plain `monthly_movement.sql` (the same query `movement`/`currencytb`/
  `currencymovement` intentionally still use) instead of the
  Closing/Opening-aware `sql/monthly_movement_v2.sql`. That reintroduced the
  already-fixed hidden-Closing-period bug (see the 2026-09-09 finding
  above) and showed up as an obviously-wrong **$24.7 billion** cell-level
  diff on December 2025 alone when diffed against the currently-published
  data — a scale no ordinary GL correction would produce. Re-fetched full
  history with `monthly_movement_v2.sql` (61,040 rows, 5 pages) and rebuilt
  `tb` again before touching the database. This is a reminder specific to
  any future full-history `tb` rebuild: `monthly_movement_v2.sql`, not
  `monthly_movement.sql`, is the correct source for `tb`.
- **Genuine FY2025 change found**: after the correction, December 2025 (and
  therefore every FY2026 period, since Balance Sheet accounts carry
  forward) differed from the previously-published data by real, moderate
  amounts — an intercompany management-fee entry between HBDM and HBDS
  (~$10.28M, accounts `4140001`/`1122125`/`6780001`/`2112105`) and a
  correction to HBDM's Corporate Taxes Payable (`2141001`, ~$18.68M) — 8
  cell diffs, ~$99M total absolute, all on HBDM/HBDS. January 2019 through
  November 2025 were byte-for-byte unchanged (spot-checked and diffed in
  full), confirming the new postings land specifically in December 2025.
  Pushed `tb` for FY2025 P12 through FY2026 P9 (the periods that actually
  changed) rather than all 93, and `movement`/`currencytb`/
  `currencymovement` for the full 2025-01 through 2026-09 window (cheap
  enough to just push, per this doc's existing "writing every period
  unconditionally is also correct, just pricier" guidance) plus a full
  `intercompany` rebuild.
- **August/September 2026 also picked up incremental drift** beyond the
  December 2025 carry-forward, on top of the fix already applied earlier
  the same day in the routine daily sync — ordinary continued backdating
  drift (same recurring pattern as every prior finding above), not related
  to the FY2025 postings specifically.
- **Validated before and after pushing**: spot-checked FY2019 P1 and
  FY2024 P12 (unaffected periods, both pre-Closing/Opening-fix and
  post-fix) matched the live-published data exactly with the corrected
  `monthly_movement_v2.sql` rebuild. Cross-checked `currencytb`/
  `intercompany` against the corrected `tb` for September 2026 (149 and
  362 combos respectively, only 7 small ($30K-$150K) mismatches — ordinary
  live-data drift from the few-minutes gap between the `monthly_movement_v2`
  fetch and the plain `monthly_movement`/`intercompany_movement` fetches,
  the same "fetch everything in the same sitting" effect documented
  2026-09-04, not a logic error) and validated Opening + Dr − Cr = Closing
  for September against August's freshly-refreshed opening (362 combos, 7
  failures, the identical 7 live-drift cells). December 2025's cross-checks
  against `currencytb`/`intercompany` show many more differences (1,313 and
  1 respectively) — expected, since `currencytb`/`currencymovement`/
  `intercompany` still use the un-fixed Closing/Opening query by design
  (documented above), so a Dec/Jan-boundary period never reconciles exactly
  between `tb` and those three collections regardless of how fresh the data
  is.

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

## Consolidated tab: historical `tb` backfill silently dropped zero-balance rows (real bug, fixed 2026-09-09)

**Report owner reported**: running the Consolidated tab for HBDM, Dec
2025, showed the Closing Balance as zero for every line — expected it to
show HBDM's real closing balance instead.

**Root cause, traced and fixed same day**: unlike the rendering bug above
(which affects the Company TB / By Currency tabs' live joins), this one is
in the historical **data itself**. Both `scripts/build_series_from_movement.py`
and `scripts/backfill_all_periods.py` — used to reconstruct the full
2019-01 through 2026-09 `tb` history from monthly Dr/Cr movement deltas —
skipped writing a period's (entity, account) row whenever its cumulative
balance netted to `abs() < 0.005` in *both* accounting and reporting
currency, even for a Balance Sheet account with a long, real history. That
condition triggers any time an account happens to net to exactly zero in
some period relative to its running total — not just "never had activity"
— so an account could silently vanish from one period's `tb` document and
reappear in a later one, violating the `tb` collection's own invariant
that once an (entity, account) has any activity it must appear in every
subsequent period, even as an explicit 0.00 (this is deliberately
different from `currencytb`, which intentionally drops near-zero currency
buckets).

- **How HBDM Dec 2025 triggered it**: Databricks confirms a large, real,
  coordinated intercompany settlement/restructuring for HBDM dated exactly
  31-Dec-2025 (dozens of paired `GJV-*` journal vouchers plus HBDM's `CLG`
  year-end closing voucher) that nets all 284 of HBDM's accounts to
  floating-point-noise-level zero that day. The buggy skip condition
  interpreted every one of those as "no balance, omit the row," so the
  entire company disappeared from that period's `tb` shard instead of
  showing 284 real $0.00 lines.
- **Scope**: not limited to HBDM or December — this triggers on any
  (entity, account, period) combination that nets to zero, which happens
  routinely. Confirmed severe corruption in `tb/2022-12` (9 rows total,
  missing nearly the entire company set), `tb/2023-12`, `tb/2024-12`, and
  `tb/2025-12` (33 rows / 6 entities, missing HBDM, HBUS, and 9 others)
  before the fix.
- **Fix**: track `first_ym`, the earliest period each (entity, account)
  ever had real movement in the raw Databricks data, and only skip a
  period if it falls *strictly before* that first activity (i.e. the
  account genuinely didn't exist yet). Never skip afterward, regardless of
  the computed balance.
- **Regeneration, not a re-query**: reused the same cached, paginated
  `sql/monthly_movement.sql` results from the original 2026-09-03/04
  backfill (62,925 rows, integrity-checked) rather than re-querying
  Databricks, so the fix is a pure recomputation from already-validated
  raw data. Regenerated all 93 periods with the fixed script.
- **Validated before publishing**: diffed the fixed Nov 2025 output
  against the previously-live data — purely additive (658 previously-
  missing keys restored, zero existing keys removed), with only 2 value
  differences, both on the HBCB/HBFR simulated Retained Earnings
  adjustment (attributable to that adjustment being recomputed against
  now-complete underlying data, not a regression). Also re-verified Opening +
  Dr − Cr = Closing across 2,047 account/entity combinations for the Dec
  2025 sample with zero mismatches.
- **What got published**: pushed the corrected 91 periods (2019-01 through
  2026-07) to the live `tb` collection, then refreshed `tb/index` with a
  matching `generatedAt`. **2026-08 and 2026-09 were deliberately excluded**
  from this push — both had already been freshly rebuilt from live
  Databricks queries earlier in the same work session (including a
  backdating-drift correction specific to August), so overwriting them with
  the cache-derived regeneration would have reverted that more recent,
  already-validated work.
- **Important caveat, not a defect**: after this fix, HBDM's Dec 2025
  Closing Balance on the Consolidated tab will still correctly show as
  ~$0.00 for virtually every line — because that genuinely is HBDM's real
  balance as of 31-Dec-2025, per the intercompany settlement described
  above. The fix corrects the report from silently hiding those accounts
  (making it look like data was missing) to explicitly and correctly
  showing them as real $0.00 lines; it does not and should not change the
  underlying value, since that value is real GL data. Worth an independent
  check with finance given the scale of the settlement, not something the
  report can or should override.
- **No republish needed**: this is a data-layer-only fix (the `tb`
  documents themselves), so the existing published report picks up the
  corrected data automatically on next load — no changes to the Artifact's
  HTML/JS were required.

## `tb` history was merging D365's hidden Closing/Opening fiscal periods into the wrong calendar month (real bug, fixed 2026-09-09)

**Report owner reported (with a real D365-generated Trial Balance Excel
export attached)**: HBDM's Dec 2025 closing balance was still wrong after
the previous fix above -- provided the exact figures D365 itself reports
for every one of HBDM's 244 accounts as of Dec 2025 P12.

**Root cause, a different and more fundamental bug than the one above**:
D365 posts two extra, hidden fiscal-calendar periods per (ledger, calendar
year) that every query in this project had been silently merging into the
wrong calendar month:

- A **"Closing" period**, dated exactly 31-Dec (same calendar date as the
  regular December period, but a *different* `fiscalcalendarperiod` recid).
  For this dataset it reverses close to the entire year's net movement for
  every account it touches, not just P&L.
- A matching **"Opening" period**, dated 1-Jan of the following year (also
  a distinct `fiscalcalendarperiod` from regular January), which
  re-establishes the true carried-forward balance for Balance Sheet
  accounts.

Every existing query (`sql/monthly_movement.sql` and everything built on
it) grouped purely by calendar `accountingdate` month, so the Closing
period's entries landed inside December's own total instead of being
excluded from it -- which is exactly what D365's own Trial Balance report
does NOT do. Confirmed directly against the report owner's Dynamics
export: D365's own period-12 report for HBDM Dec 2025 matches our numbers
only once the Closing-period rows are removed from that period's
cumulative.

**A Closing/Opening period is detected generically**, per (ledger,
calendar year), with no hardcoded recids: group by
`(ledger, fiscalcalendarperiod, calendar_year)`, computing
`MAX(accountingdate)` and `COUNT(DISTINCT accountingdate)`; filter to
groups whose `MAX(accountingdate)` is 12-31; the group with fewer distinct
accounting dates than the "regular" period-12 group (which spans the whole
month) is the Closing period.

**Fix**, implemented in the new `sql/monthly_movement_v2.sql` (supersedes
`sql/monthly_movement.sql` as the source for `tb`):
- **Balance Sheet accounts** (1,000,000-3,999,999): Closing-period rows are
  re-bucketed into January of the *following* year -- excluded from the
  closing year's own December cumulative (matching D365's own report) but
  still counted from the next period onward (the entry is real money
  movement, just administratively dated to a period D365 excludes from its
  own year-end report).
- **P&L accounts** (>= 4,000,000): Closing-period rows are dropped
  entirely. The existing build already resets P&L to zero every January;
  the Closing period's job for a P&L account is exactly that reset, so
  including it would double it.

**Two dead ends before landing on the shift-vs-drop fix**, worth recording:
first tried simply excluding all years' Closing-period entries outright
(not shifting them), which produced cumulative balances far too large
(e.g. $16,196,827.30 instead of the correct $6,038,816.37 for one HBDM
account) -- a debug query showed each year's Closing-period delta exactly
cancels that *same* year's own non-closing delta, proving a temporary
same-year reversal that needs to be moved forward, not permanently
dropped. A first draft of the detection query also ranked *every* period
active in a year by distinct-date count, misidentifying ordinary
low-activity months as "closing" -- fixed by first filtering to only the
periods whose latest date is 12-31 before ranking.

**Validated to the cent against the report owner's own Dynamics export**:
all 244 accounts in HBDM's Dec 2025 export match exactly -- 128/128
Balance Sheet accounts exact, P&L accounts exact once correctly
year-scoped.

**A second, unrelated bug was caught and fixed during the rebuild**:
refetching 61,000 rows of full history via several independent
`ROW_NUMBER()`-paginated queries, run as separate tool calls minutes
apart, is unsafe against ongoing GL writes -- an earlier-sorting entity's
row count changing between calls shifts the global row numbering, silently
duplicating/dropping rows at page boundaries with no detectable integrity
failure (the `rn` sequence itself still looks like a complete, gap-free
1..N run). Diagnosed via a persistent $1.4M HBFZ control-total imbalance
traced to one missing (entity, account, period) row. Fixed by re-fetching
each entity's full history via its own self-contained, single-entity-scoped
query (`WHERE gje.ledger = <that entity's ledger id>`), immune to other
entities' data changing between calls; only HBFZ needed its own internal
pagination (17,943 rows), done as two calls scoped to HBFZ alone,
integrity-checked for zero gaps/duplicates.

**What got published**: pushed the corrected 91 periods (2019-01 through
2026-07) to the live `tb` collection via 16 atomic batch writes, then
refreshed `tb/index`. **2026-08 and 2026-09 were deliberately excluded**,
same reasoning as the fix above -- both had already been freshly rebuilt
from live Databricks queries earlier in the work session and would be
reverted by the cache-derived regeneration. Spot-checked the live
read-back after publishing (HBDM account `1112005`, Dec 2025) against the
Dynamics export figure and confirmed an exact match.

**No republish needed**: this is a data-layer-only fix (the `tb`
documents themselves) -- the existing published report picks up the
corrected data automatically on next load.

## `movement` collection (Company TB Dr/Cr) had the same Closing/Opening bug -- fixed 2026-09-09, later same day

**Report owner reported**: HBDM Dec 2025, account `1111001` Petty cash --
Company TB showed Current Month Dr 13,789.55 / Cr 13,789.55 (netting to
zero), but the Dynamics export shows Debit 265.51 / Credit 0.00. Closing
Balance (265.52) was already correct on both sides -- only Dr/Cr disagreed.

**Root cause**: exactly the caveat flagged in the finding above. The
`movement` collection (Company TB's Current Month Dr/Cr, and by extension
`currencytb`/`currencymovement` for By Currency and Transaction Currency)
is built from `sql/monthly_movement.sql`, which still groups by calendar
`accountingdate` month and so still merges each ledger's Closing-period
entries into December's own Dr/Cr total -- the same bug `tb` had, just not
yet ported to this collection. For HBDM Dec 2025 Petty cash, the
Closing-period entries added extra offsetting Dr and Cr that should have
been excluded (they reverse close to each other, per the same-year
cancellation behavior described in the finding above) -- which is why
Closing Balance still looked right (opening + net movement was unaffected)
while the individual Dr and Cr figures were each inflated and wrong.

**Fix**: rebuilt `movement` from the SAME already-fetched, already-
corrected `sql/monthly_movement_v2.sql` data used for the `tb` fix above
(the per-entity-scoped fetch cached at that point already contains
per-period Dr/Cr with Closing-period entries shifted/dropped -- no new
Databricks query needed). Ran the existing `scripts/build_monthly_movement.py`
unchanged against that data (its input shape -- entity_code, mainaccountid,
ym, debit_acc, credit_acc, debit_rep, credit_rep -- was already correct;
only the SQL feeding it needed the v2 fix), then
`scripts/prepare_movement_writes.py` -> 91 periods, 187 document writes
across 18 batches, pushed live (same 2026-08/2026-09 exclusion as the `tb`
push, for the same reason).

**Validated**: HBDM Dec 2025 Petty cash now shows Debit 265.514 / Credit
0.00 in the live `movement/2025-12` shard -- an exact match to the
Dynamics export. Broader check across all 61,015 (entity, account, period)
rows using the same already-published `tb` closing balances as ground
truth (Opening = prior period's `tb` closing, 0 for P&L accounts in
period 1; expected = Opening + Dr - Cr, reporting currency): 61,006 of
61,015 combos reconcile exactly; the 9 exceptions are all HBBV, all in
2026-05/2026-07/2026-08/2026-09, and all trace to HBBV's own
already-documented reporting-currency-fallback quirk (`gjae.reportingcurrencyamount`
is null/0 for HBBV since it has no reporting currency configured in D365,
so `movement`'s raw reporting-side sum is 0 while `tb`'s closing balance
correctly substitutes the accounting-currency amount) -- confirmed
unrelated to this fix by checking the same 9 combos on the
accounting-currency side, where they reconcile exactly.

**`currencytb`/`currencymovement` (By Currency tab, Company TB's
Transaction Currency mode) still have the analogous bug** -- they're built
from `sql/monthly_movement_by_currency.sql`, a different query with the
transaction-currency dimension added, which was not touched in this pass.
Fixing it needs a `monthly_movement_by_currency_v2.sql` (same Closing/Opening
detection and shift/drop logic, plus the `txn_ccy` grouping column) and a
fresh Databricks fetch, since the cached v2 data doesn't carry transaction
currency. Not done here since the report owner's ask was specifically
about Company TB; worth a follow-up pass if By Currency shows the same
symptom.

**No republish needed**: data-layer-only fix (the `movement` documents
themselves) -- the existing published report picks up the corrected data
automatically on next load.

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

## 2026-09-11: Vendor Balance / Customer Balance backfilled for all 93 periods

The published report had already grown live "Vendor Balance" and
"Customer Balance" tabs (built in a separate, concurrent session) before
any of their SQL, build scripts, or data existed in this repo or in this
session's history — discovered only because the report owner could see
data for Sept 2026 but nothing for any earlier period. Reverse-engineered
the entire data model from the live artifact's own JS (field names,
collection/shard layout, filtering rules) since no source SQL existed
anywhere, then wrote `sql/vendor_balance.sql`, `sql/customer_balance.sql`,
and their `_by_currency` counterparts (documented above under "What's
here"), plus `scripts/build_party_balance_periods.py` and
`scripts/prepare_party_balance_writes.py`.

**Two data bugs found and fixed in the process, neither caused by this
session's own code:**

1. **`vendtable`/`vendtrans` `dataareaid` case mismatch** (this session's
   own SQL, caught before push) — see `sql/vendor_balance.sql`'s entry
   above. Fixed by joining case-insensitively; re-fetching after the fix
   changed Sept-2026 vendor row count from 16,640 to 27,055 (balance) and
   17,474 to 28,280 (currency).
2. **The other session's Sept-2026 customer snapshot used the wrong
   cutoff date.** Manually reconstructed HBCB/C000002's balance from all
   37 raw `custtrans` rows via running-total arithmetic: the correct
   Sept-2026 balance is 3,349,900, but the currently-published snapshot
   showed -2,650,100 — tracing the running total showed that figure
   matches the balance as of roughly 2026-04-01 to 2026-04-09, not
   September, despite being labeled as the current period. This is
   corrected automatically by the full rebuild below (this session never
   read or reused the other session's logic, so there was nothing to
   patch in code — only to overwrite with a correct fetch).

**Backfill**: fetched full-history (2019-01 through 2026-09) vendor and
customer data in both grains (balance + by-currency, 4 fetches total,
paginated), forward-summed into 93 monthly periods per collection with
`build_party_balance_periods.py`, sharded with
`prepare_party_balance_writes.py`, and pushed via 19 `write_db` batches
(5 vendor-balance, 6 vendor-currency, 4 customer-balance, 4
customer-currency — split below the ~1MB per-request `write_db` limit,
not just the 50-write cap). All batches are idempotent `set`s, so no
data-loss risk from the two grains' writes overlapping the same period
document.

**Repo sync**: `report/consolidated-trial-balance.html` in this repo had
also drifted stale relative to the published artifact — it had zero
references to "vendor" or "customer" at all, missing not just this
backfill's data but the entire Vendor/Customer Balance tab UI/JS added by
the other session. Diffed the full published artifact HTML against the
local file: the local copy was a strict subset (every difference was a
published addition, nothing local-only would have been lost), so it was
safe to overwrite `report/consolidated-trial-balance.html` wholesale with
the current published content.

## 2026-09-16/17/18: backdated postings into an ALREADY-PUBLISHED "closed" period -- a new, more severe drift category

Prior sessions had documented *intra-session* drift (the same GL query
returning different numbers minutes apart, because new postings landed
mid-fetch -- see the September 2026 sync entries above). This firing's
full, non-sampled Opening + Dr - Cr = Closing validation (every
(account, entity) combo, not a sample) surfaced something worse: **a
period we had already published as "closed" (August 2026, `tb/2026-08`,
`generatedAt: 2026-09-14T12:03:52Z`) was stale by the time September's
sync ran**, because new GL lines had been posted in D365 *after* that
publish, dated *inside* August.

**How it was found.** The validation compared September's freshly-fetched
closing balance against `stored August closing (Opening) + September's
Dr/Cr movement`. Two separate query fetches for September (tb closing,
then movement) initially disagreed with each other -- diagnosed first as
the familiar intra-session drift and "fixed" by computing both in a
*single* SQL execution (one `filtered` CTE, two aggregates over the same
read, so both numbers reflect one atomic snapshot -- see
`sql/consolidated_trial_balance.sql`'s comment header for why a lower
bound on `accountingdate` alone isn't enough). That eliminated the
query-to-query race, but 24 (account, entity) combos *still* failed to
reconcile. Every one of the 24 was explained by re-fetching August's
closing fresh (same single-query method, `accountingdate < 2026-09-01`)
and diffing it against the currently-stored August closing: the fresh
number differed from the stored one by exactly the validation gap, for
all 24 keys, no exceptions. August itself had moved.

**Root cause, confirmed at the line level.** `hb_catalog.db_bronze_d365.
generaljournalentry` has a real, populated `createddatetime` column (a
"row created in the source system" audit timestamp, distinct from
`accountingdate`, the user-chosen posting date). Note:
`generaljournalaccountentry.createddatetime` is a dead sentinel
(`1900-01-01` on every row seen) -- it is `generaljournalentry.
createddatetime` (the parent journal header) that carries the real
audit trail. Querying account 1122012 ("Inter Company Receivable - HB UK
Holding Co. Ltd.") / entity HBDM directly: eight lines with
`accountingdate = 2026-08-31` all show `createddatetime =
2026-09-16T08:15:43Z` -- created two days *after* our August tb was
published on 2026-09-14. These are genuine backdated entries (an
intercompany settlement/clearing batch, by the look of the affected
accounts -- see below), not a query bug, not IsDelete/CLG artifacts, and
not the previously-documented HBCB/HBUK/HBFR control-total exceptions
(those three are excluded from this validation as already-known and
already-simulated-adjusted).

**Scope of the August drift**: exactly 24 (account, entity) keys, all
intercompany-clearing-shaped pairs across a handful of ledgers (HBDM,
HBUK, HBDS, HBFR) -- receivable/payable mirrors (1122xxx/2112xxx),
cost-of-goods/inventory clearing pairs (1131xxx/2232xxx/5110xxx). Every
key's August delta, once corrected, exactly closed the September
validation gap for that key (verified: re-running Opening + Dr - Cr =
Closing across all 1,730 non-adjustment combos after the fix produced
**0 failures**, down from 24).

**Fix applied**: re-fetched August 2026 in full (same single-query,
`accountingdate < 2026-09-01`, all 1,729 (account, entity) rows, not
just the 24 known-drifted ones, in case there were others -- there
weren't), re-applied the same three simulated adjustments
(HBCB/HBUK/HBFR on 3141001, same script, same order, same dynamic
sizing), and republished `tb/2026-08` (`if_version`-pinned, v16 -> v17).
September's `tb`, `movement`, `currencytb`, and `currencymovement` were
then rebuilt from a fresh combined fetch (closing + movement computed in
one query execution, extended to also carry `transactioncurrencyamount`
and currency code so `currencytb`/`currencymovement` came from the exact
same atomic read as `tb`/`movement` -- eliminating the cross-collection
staleness that a separate later fetch would reintroduce) and pushed
(`tb` v20->21, `movement` v13->14, `currencytb` v15->16,
`currencymovement` v14->15). `tb/index`'s `generatedAt` was updated for
both `2026-08` and `2026-09`.

**Methodology change going forward -- read before the next daily sync:**
whenever this routine needs both a *closing* balance and a *movement*
(Dr/Cr) figure for the same period, or a cross-check between two
collections (e.g. `tb` vs `currencytb`), compute all of them **in one
SQL query execution** (one `filtered` CTE, multiple `SUM(CASE WHEN ...)`
aggregates over the same read) rather than issuing separate queries and
trusting them to agree -- two separate `execute_sql_read_only` calls,
even seconds apart, are NOT guaranteed to see the same snapshot of a
live, actively-posted-to bronze table. This was previously worked around
by fetching "fast" or "tight window"; a single combined query removes
the race entirely rather than narrowing it.

**Open follow-up, not yet built**: `gje.createddatetime` (real,
populated) is a much cheaper way to catch this class of drift than a
full historical re-fetch and a 1,730-key reconciliation. A lightweight
nightly check --
`SELECT ... FROM generaljournalentry WHERE createddatetime >=
current_date() - INTERVAL 30 DAYS AND accountingdate < <first day of the
current open period>` -- would surface exactly this kind of backdated
posting into an already-published period within a day of it happening,
before it has to be caught by a full reconciliation days later. Not
implemented yet (this firing ran out of scope for it); the next
person/session picking this up should consider adding it as an
additional daily-sync step, run against every already-published period,
not just the immediately-prior one.

## 2026-09-18: Vendor Balance / Customer Balance refreshed for the first time since the 2026-09-11 backfill

The 2026-09-11 backfill (see that heading above) has never been touched by
the daily refresh procedure -- `vendor`/`customer` are not part of the
four-collection daily sync (`tb`/`movement`/`currencytb`/`currencymovement`),
so they'd been sitting on data as of 2026-09-10/11 for a full week while
FY2026 P9 kept accumulating real AP/AR activity, and per this doc's
well-established backdating pattern, August had every reason to have moved
too.

**Approach used -- targeted refresh, not a full-history rebuild.** A quick
count confirmed the two-month movement window is tiny (543 vendor-balance
rows, 588 vendor-currency rows, 169 customer-balance rows, 205
customer-currency rows for Aug+Sep combined, all comfortably one page), so
rather than re-fetching all of 2019-01 through 2026-09 again,
`sql/vendor_balance.sql` / `sql/customer_balance.sql` /
`_by_currency` variants were each run ONCE with `{{RANGE_START}} =
2026-08-01`, `{{RANGE_END_EXCLUSIVE}} = 2026-10-01` (both months in a single
query execution per grain, per this doc's "fetch related things together"
rule), and forward-summed on top of the currently-stored **2026-07**
balance as the seed (one already-settled period back from the two being
refreshed) -- the same forward-sum arithmetic
`build_party_balance_periods.py` uses, just seeded from an existing
balance instead of from zero at ledger inception. This is a one-off
adaptation script (`scripts` directory unchanged), not a permanent
replacement for the full-history scripts.

**Validated against direct Databricks queries before trusting the
forward-sum, not just assumed correct**: spot-checked three flagged
(entity, account) keys with a full-history-to-date cumulative query run
directly against `vendtrans`/`custtrans` (no forward-summing) --
HBUK/V000032 (a large swing), HBDM/V000015 (dropped to zero), and
HBDM/C000004 (a large customer swing) -- all three matched the forward-summed
September figure to the cent. The swings themselves are genuine: e.g.
HBUK/V000032's real August net movement was -48,728,629.90 (accounting) /
-65,999,886.25 (reporting) on its own -- a large number for one vendor in
one month, but confirmed real, not a join fan-out (checked `vendtable` for
that vendor/company: exactly one master record, no duplicate-casing rows
to double-count).

**What was found (stored vs. freshly computed), before pushing:**

| Grain | Period | Stored rows | Computed rows | Added | Removed | Changed | Total abs $ drift |
|---|---|---:|---:|---:|---:|---:|---:|
| vendor balance | 2026-08 | 233 | 233 | 0 | 0 | 48 | $162.3M acc / $140.2M rep |
| vendor balance | 2026-09 | 265 | 236 | 22 | 51 | 63 | $183.3M acc / $150.2M rep |
| vendor currency | 2026-08 | 466 | 467 | 1 | 0 | 18 | $160.7M |
| vendor currency | 2026-09 | 499 | 474 | 23 | 48 | 61 | $171.0M |
| customer balance | 2026-08 | 145 | 145 | 0 | 0 | 6 | $239.1M acc / $67.3M rep |
| customer balance | 2026-09 | 146 | 148 | 2 | 0 | 42 | $256.8M acc / $83.6M rep |
| customer currency | 2026-08 | 275 | 276 | 1 | 0 | 11 | $240.9M |
| customer currency | 2026-09 | 277 | 280 | 3 | 0 | 53 | $257.1M |

September moved more than August in every grain (expected -- it's the
still-open current period accumulating the most new activity, on top of
carrying forward whatever else changed in August). The largest single
driver was HBDM/C000004 (a customer intercompany account) swinging from
-$104.4M to +$132.7M reporting-currency-equivalent -- a genuine ~$237M
correction, confirmed against the direct cumulative query. Several HBUK
vendor accounts (intercompany-shaped, V000032/V000151/V000036/V000034/etc.)
also moved by tens of millions each, consistent with this being the same
kind of intercompany settlement/backdating activity already documented
repeatedly above for `tb`/`intercompany`.

**Pushed**: one atomic 12-write `batch` (both period docs + both shard
docs, balance and currency grain, for both `vendor` and `customer`,
2026-08 and 2026-09), every entry `if_version`-pinned to the version read
moments before
(`vendor/2026-08` v2->v3, `vendor/2026-09` v3->v4, `customer/2026-08`
v2->v3, `customer/2026-09` v3->v4, all eight shard/currency-shard docs
v1->v2 or v2->v3 as applicable). All four collections still fit in exactly
one shard and one currency-shard per period (largest, vendor currency
Sept, is ~76KB -- nowhere near the ~200KB per-document guidance this repo
uses elsewhere), so no new sharding logic was needed.

**Not done, left for a future pass**: a full-history (2019-01 onward)
re-verification of `vendor`/`customer` -- this refresh only touched
2026-08/2026-09 per the task's minimum bar, seeded from the currently
stored 2026-07 balance, which was trusted as settled rather than
independently re-derived. If `vendor`/`customer` are added to the daily
four-collection sync going forward (recommended, given they've now
independently confirmed the same backdating pattern `tb` already has),
that trust assumption goes away since each day's sync would only need to
carry one month's seed forward from the day before.

## 2026-09-18 daily sync: `intercompany` full-history rebuild only

Scoped strictly to step 5 of the daily procedure -- `tb`, `movement`,
`currencytb`, `currencymovement`, `vendor`, and `customer` were left
untouched (owned by other concurrent workstreams today, including one
fixing small `tb` backdating drift on FY2026 P4-P7).

Re-ran `sql/intercompany_movement.sql` in full (5,644 rows, not
truncated) via `execute_sql_read_only`, then
`scripts/build_intercompany_periods.py --latest-ym 2026-09` to rebuild
all 93 periods (2019-01 through 2026-09) from that one fetch, then
`scripts/prepare_intercompany_writes.py` to shard the output.

**Diffed before writing** rather than pushing unconditionally: fetched
every one of the 93 currently-stored `intercompany/<period>/shards/0`
documents (all were at a uniform version 6, confirming the doc's note)
and compared them field-by-field against the freshly rebuilt output.
**91 of 93 periods (2019-01 through 2026-07) were byte-identical** --
only **2026-08 and 2026-09 had changed**, both driven by ordinary
HBUK-side GL activity landing between the last `intercompany` rebuild
and today (e.g. `1122005`/`1122105` and `2112005`/`2112105` HBUK pairs
shifted by ~$2.68M/$3.1M accounting-currency; `2112123`/HBFR and
`2112123`/HBUK also moved in September). Largest single-cell drift seen:
~$4.77M (accounting currency) on a September HBFR/HBUK combination.
Pushed only those two changed period shards via one atomic
`ArtifactData` batch write, each pinned with `if_version: 6` (both
succeeded, now at version 7); the two period-index docs
(`fiscalYear`/`period`/`shardCount`) were unchanged (`shardCount` stays
1 for both) so were not rewritten.

**Cross-check against `tb/2026-09`**: re-read `tb/2026-09` and its shard
fresh (per the note that another workstream validated August/September
`tb` clean this morning -- confirmed: `generatedAt` was
2026-09-18T12:28:02Z, i.e. from this morning's `tb` sync, not stale).
Summed `intercompany`'s 2026-09 accounting-currency values across all 41
accounts / 148 (account, entity) pairs and compared against `tb`'s value
for the same mainaccountid/entity combinations: totals matched to
$0.02 (a sub-cent floating-point rounding artifact on 4 of the 148
pairs, reporting-currency only, each off by $0.01) -- no real drift, no
missing accounts either direction.

No changes made to any other collection or to the report HTML.

## 2026-09-18: `tb` backdating drift fixed for FY2026 P4-P7, plus a December 2025 anomaly found and deliberately NOT fixed

Following the 2026-09-16/17/18 backdating-into-published-period incident
documented above, this session ran the same single-combined-query
methodology across every period a fresh `generaljournalentry.createddatetime
>= 30 days ago` scan flagged as touched: 2025-12, 2026-01 through 2026-09
(the `createddatetime` scan itself found small counts of new postings --
8 to 103 lines -- landing as far back as **2025-12 and every month of
2026 through June**, not just the current/prior period the old "spot-check
the prior period only" heuristic checked. This is the concrete case for
building the createddatetime-scoped procedure below).

**Real drift found and fixed, FY2026 P4-P7**: 8-11 (account, entity)
combinations per period, $4.5M-$22M each, same recurring
intercompany-clearing-shaped pattern as every prior finding in this doc.
Fixed by patching only the drifted cells (not a full period rebuild) in
each period's shard, pinned `if_version` (all four periods were at
shard/period version 8, now version 9).

**2026-01 through 2026-03 and 2026-08/2026-09**: re-checked, zero drift
(08/09 already corrected by the 09-16/17/18 fix; 01-03 apparently settled
since original backfill).

**2025-12 anomaly -- found, NOT fixed, needs dedicated follow-up.** A
direct single-query cumulative-through-2025-12 fetch returned **0.00**
for roughly 1,300 of 2,179 (account, entity) combinations that the
currently-stored `tb/2025-12` shows large nonzero balances for -- several
in the hundreds of millions to ~$1.5B on individual cells (e.g.
`1131022`/HBFZ: fresh $0.00 vs. stored $1,547,724,999.84). Traced one
flagged account (`1131022`/HBFZ, ledger 5637145327) back to raw
`generaljournalaccountentry` history: it shows a large negative entry
every December, reversed by an equally large positive entry the
following January, every year from 2019 through 2025 -- consistent with
this being a real, self-cancelling annual pattern (this account nets to
~$0 cumulative through any December, by design), which would mean the
**freshly computed $0.00 is correct and the currently-stored ~$1.5B
figure is the one that's wrong** -- likely inherited from the
2026-09-10 full-history rebuild's `monthly_movement_v2.sql`
Closing/Opening-period handling (see that date's entry above), which
this doc already flagged once for a different, since-fixed December
bug. This was NOT pushed as a fix in this session: the dollar amounts
are too large and the diagnosis too shallow (one account traced, not
all ~1,300) to correct blind. **Next session or a dedicated
investigation should**: (a) pull the full raw history for a sample of
the ~1,300 flagged (account, entity) pairs the way `1131022`/HBFZ was
traced here, (b) confirm the self-cancelling year-end pattern holds
generally (not just for this one account), and (c) if confirmed,
rebuild `tb/2025-12` (and, since Balance Sheet accounts carry forward
cumulatively, re-validate whether this cascades into 2026-01 onward --
though the 2026-01/02/03 direct-fetch checks above found zero drift
against currently-stored data, which would mean either the bad
December value doesn't actually propagate, or both the stored December
AND the stored January-March values share the same wrong basis and
happen to net out consistently -- this needs to be checked explicitly,
not assumed).

## 2026-09-18: Sync cadence changed to 4x/day, createddatetime-scoped

Per the report owner's explicit request, the "Daily consolidated trial
balance sync" Routine was changed from once daily (04:00 UTC) to four
times a day (~8am, 12pm, 2pm, 5pm UAE time = 04:00/08:00/10:00/13:00
UTC), and renamed "Intraday trial balance sync (4x/day,
createddatetime-based)". Its stored prompt was rewritten to point at
this new procedure instead of the old always-full "Daily refresh"
section above.

**New standard procedure for routine firings** (the "Daily refresh"
section above remains the reference for a full manual deep-audit, but is
no longer what every firing runs):

1. Query `generaljournalentry` for `createddatetime >= current_date() -
   INTERVAL 30 DAYS`, grouped by `date_format(accountingdate, 'yyyy-MM')`,
   to find every accounting period with new or backdated activity in the
   last 30 days -- not just the current and immediately-prior period.
   This session's own run of this exact query is what surfaced the
   2025-12 anomaly and the FY2026 P4-P7 drift above, both of which the
   old "spot-check the prior period only" heuristic would have missed
   entirely.
2. For every flagged period, recompute closing + movement (Dr/Cr) +
   currency breakdown in **one single combined SQL query execution**
   (one `filtered`/`scoped` CTE, multiple `SUM(CASE WHEN ...)`
   aggregates) -- never as separate queries, per this doc's
   already-documented race-condition history (see the 2026-09-16/17/18
   entry above). When multiple periods are flagged in the same fiscal
   year, they can be computed in the SAME query execution too (add one
   more pair of `SUM(CASE WHEN accountingdate < <cutoff> ...)` columns
   per period cutoff) -- this session did exactly that across 10 periods
   in one query/pagination pass.
3. Diff the fresh result against currently-stored `tb` (and
   `movement`/`currencytb`/`currencymovement`/`intercompany` for periods
   where those are also affected) and push **only the cells that
   actually drifted**, not a full period rebuild -- cheaper, and the
   diff itself is the audit trail for what changed.
4. Update `tb/index`'s `generatedAt` only for periods actually touched.
5. Validate Opening + Dr - Cr = Closing across every (account, entity)
   combination in every period touched (not sampled) before considering
   the firing done.
6. If a discovered anomaly looks too large or too uncertain to fix
   confidently in one firing (see the 2025-12 anomaly above), leave it
   documented and unfixed rather than guessing -- a wrong "fix" pushed
   to a live financial report is worse than a known, flagged gap.

**Vendor Balance / Customer Balance are still not part of either the
old daily or the new intraday procedure** -- they were refreshed once
this session (see the entry above) as a one-off catch-up, but adding
them to the recurring procedure (both old and new) is still open follow-up
work, not yet done.

## 2026-09-19: First two intraday firings under the new 4x/day cadence

**08:07 UTC firing (~12:07pm UAE):** ran the createddatetime-scoped scan
(30-day window). No new activity in any previously-flagged older period
(2025-12 through 2026-06, 2026-08 all unchanged since the prior day's
full pass) -- confirms yesterday's fixes held. Only `2026-09` (the
current, still-open period) had moved, via ordinary same-day GL
accumulation (36,011 -> 36,026 lines in the 30-day window). Recomputed
September's closing via a single combined query (3,317 rows across 2
pages, same account/entity/txn_ccy grain as the 2026-09-18 fixes) and
found **88 (account, entity) cells drifted** by up to ~$1.06M each --
almost entirely HBDS-side accounts (`1131022`/`2232001`/`2232002` and
related clearing/cash pairs), consistent with continuous
intercompany-settlement-shaped activity already documented repeatedly in
this file. Patched just those 88 cells in `tb/2026-09`'s shard
(version 21->22), updated the period doc's and `tb/index`'s
`generatedAt`. `movement`/`currencytb`/`currencymovement` for the same
period were handed to a background workstream to rebuild from the same
underlying data (see below if a separate entry for that appears).

This is the first live proof the new cadence does what it was built
for: a targeted, few-minute check every ~4 hours catches same-day
intraday drift that the old once-a-day cadence would have let
accumulate for up to 24 hours before catching.
