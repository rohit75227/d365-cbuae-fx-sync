-- ============================================================================
-- Customer Aging: open AR items grouped by (legal entity, customer, due
-- date) -- Databricks SQL (hb_catalog.db_bronze_d365)
-- ============================================================================
-- Feeds the "Customer Aging" tab (the "customerAging" collection). Unlike
-- every other collection in this report, this is NOT period-scoped -- it is
-- a live snapshot of currently-open receivables, re-fetched in full on every
-- sync (no {{RANGE_START}}/{{RANGE_END_EXCLUSIVE}} tokens). Aging bucket
-- assignment (0-30/31-60/61-90/91-180/180+/Not Due) is deliberately NOT done
-- here -- it is computed client-side from `due_date` against whatever
-- "as on date" the report viewer picks, the same reasoning
-- docs/trial-balance-setup.md gives for Company TB's date range: baking a
-- bucket into the stored data would freeze it to the sync date.
--
-- Three judgment calls, verified live against this data on 2026-09-19
-- before trusting them (see docs/trial-balance-setup.md's dated entry):
--
-- 1. "Open" = custtrans.closed carries a dead-sentinel timestamp
--    (1900-01-01), not SQL NULL, when a transaction is not yet closed --
--    same sentinel-instead-of-NULL pattern this repo already documented for
--    generaljournalaccountentry.createddatetime. A real (non-sentinel) date
--    means the item was fully settled as of that date.
--
-- 2. Only rows with a non-blank `invoice` number are included. Checked
--    live: of the 7 distinct custtrans.transtype values appearing among
--    currently-open rows, only transtype 2 (Invoice, 48,848 open rows),
--    8 (613 rows), 251 (30 rows) and 14 (2 rows) carry an invoice number at
--    all -- transtypes 15/36/12 (2,194 / 982 / 112 rows) never do, and
--    transtype 36 alone accounts for $6.8B of *self-cancelling* gross
--    remaining amount (nets to only $155M) against a $1.46B net for
--    transtype 2 with no such cancellation -- consistent with 15/36/12
--    being clearing/write-off/on-account journal postings to the customer
--    subledger rather than individually dated, agable invoices. Excluding
--    them is a deliberate scope decision (an aging report buckets dated
--    invoices, not clearing entries), not an oversight; if a future sync
--    ever needs the excluded universe, `invoice IS NULL` is the way back in.
--
-- 3. Remaining amount = amountmst - settleamountmst (amountcur's cumulative
--    settled-to-date field), NOT settleamountmst added -- verified live:
--    summing ABS(amount - settle) over CLOSED (non-sentinel) transactions
--    gives ~$909M total (small residual across 5.14M closed rows, mostly
--    FX/rounding trueups), vs. ~$67.9B if settleamountmst were added
--    instead -- confirms subtraction is the correct sign convention.
--
-- Region comes from custtable.ltregion (an existing custom field, values
-- like "Europe", "North America", "MEASAT", "Intercompany" -- confirmed
-- live 2026-09-19, ~58 of several hundred customers have it NULL, mapped to
-- "(No Region)" here rather than dropped).
--
-- Report-owner request (2026-09-19): exclude Intercompany, Influencers, and
-- Internal Request Orders entirely -- these aren't third-party trade
-- receivables an AR aging review cares about. Intercompany is excluded by
-- TWO rules, not just the region tag: the report owner clarified that any
-- customer account starting with "C" is intercompany regardless of what
-- `ltregion` says -- checked live: 294 customers have an accountnum
-- starting with "C", of which 271 are already tagged region=Intercompany,
-- but 17 sit at "(No Region)" and 6 at other regions (E-Commerce/Staff
-- Sales) despite being intercompany by code -- the region tag alone would
-- have missed those. Both rules are applied (region match OR
-- accountnum-starts-with-C) so either signal is enough to exclude a row.
--
-- Grain: one row per (legal_entity, customer_account, due_date) -- invoices
-- sharing a customer+due-date are summed together (1,605 combos before
-- this exclusion, as of 2026-09-19, comfortably one page -- no pagination
-- needed, unlike every other query in this repo).
-- ============================================================================

WITH filtered AS (
    SELECT
        UPPER(ct.dataareaid)                 AS legal_entity,
        ct.accountnum                        AS customer_account,
        dp.name                               AS customer_name,
        cd.custgroup                          AS customer_group,
        COALESCE(cd.ltregion, '(No Region)')  AS region,
        ct.duedate                            AS due_date,
        (ct.amountmst - COALESCE(ct.settleamountmst, 0))                 AS remaining_acc,
        (ct.reportingcurrencyamount - COALESCE(ct.settleamountreporting, 0)) AS remaining_rep
    FROM hb_catalog.db_bronze_d365.custtrans ct
    JOIN hb_catalog.db_bronze_d365.custtable cd
        ON cd.accountnum = ct.accountnum AND cd.dataareaid = ct.dataareaid
    LEFT JOIN hb_catalog.db_bronze_d365.dirpartytable dp
        ON dp.recid = cd.party
    WHERE COALESCE(ct.IsDelete, false) = false
      AND LOWER(ct.dataareaid) NOT LIKE 'ky%'
      AND ct.closed < TIMESTAMP'1990-01-01'
      AND ct.invoice IS NOT NULL AND ct.invoice != ''
      AND COALESCE(cd.ltregion, '(No Region)') NOT IN ('Intercompany', 'Influencers', 'Internal Request Orders')
      AND ct.accountnum NOT LIKE 'C%'
),
grouped AS (
    SELECT
        legal_entity,
        customer_account,
        MAX(customer_name)  AS customer_name,
        MAX(customer_group) AS customer_group,
        MAX(region)         AS region,
        due_date,
        SUM(remaining_acc) AS remaining_acc,
        SUM(remaining_rep) AS remaining_rep,
        COUNT(*) AS invoice_count
    FROM filtered
    GROUP BY legal_entity, customer_account, due_date
)
SELECT *
FROM grouped
WHERE ABS(remaining_acc) > 0.005 OR ABS(remaining_rep) > 0.005
ORDER BY legal_entity, customer_account, due_date;
