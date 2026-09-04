-- ============================================================================
-- Monthly Dr/Cr movement — Databricks SQL (hb_catalog.db_bronze_d365)
-- ============================================================================
-- Feeds the "Company TB" tab's Current Month Dr / Current Month Cr columns.
-- Same entity mapping, IsDelete, and account-range rules as
-- consolidated_trial_balance.sql (see that file's header for why each rule
-- exists -- gje.ledger for entity attribution, gje.accountingdate not the
-- fiscal RECID columns, no CLG exclusion).
--
-- Unlike the main query, this is NOT split into BS/PL buckets with different
-- period logic, because it produces a single month's raw movement rather
-- than a cumulative balance -- "this account moved $X debit / $Y credit in
-- March 2024" is the same computation whether the account is Balance Sheet
-- or P&L. The BS-vs-PL distinction (cumulative-since-inception vs.
-- fiscal-year-to-date) only matters when *accumulating* these monthly
-- deltas into a balance, which the report does client-side by adding this
-- month's movement to the prior period's stored closing balance (or to 0 in
-- January, for P&L).
--
-- Dr/Cr split uses the SIGN of the signed amount columns (positive =
-- debit, negative = credit), NOT the `iscredit` flag -- verified live that
-- `iscredit` disagrees with the amount's sign on ~2.9% of rows (likely
-- corrections/reversals), and the signed amount is what the already-live
-- and validated closing balances are computed from (SUM(amount) net). Using
-- `iscredit` instead would make Opening + Dr - Cr != Closing for those
-- rows. Using the sign keeps this exactly consistent with the existing,
-- validated trial balance by construction.
--
-- Grain: one row per (entity_code, mainaccountid, ym) where ym is
-- 'YYYY-MM'. ~62,755 rows across 2019-01 through 2026-08 as of 2026-09-04 --
-- paginate with the ROW_NUMBER() pattern (12,288-row cap) same as the
-- balance backfill.
--
-- Substitution tokens (replaced by scripts/render_query.py):
--   {{RANGE_START}}            -- inclusive, e.g. TIMESTAMP'2019-01-01T00:00:00Z'
--   {{RANGE_END_EXCLUSIVE}}    -- exclusive, e.g. TIMESTAMP'2026-09-01T00:00:00Z'
--   {{PAGE_START}} / {{PAGE_END}} -- inclusive rn bounds for one page
-- ============================================================================

WITH filtered AS (
    SELECT
        ma.mainaccountid AS mainaccountid,
        ma.name          AS mainaccountname,
        CASE gje.ledger
            WHEN 5637145326 THEN 'HBDM'
            WHEN 5637145327 THEN 'HBFZ'
            WHEN 5637145328 THEN 'HBUS'
            WHEN 5637145329 THEN 'HBLL'
            WHEN 5637145330 THEN 'HBUK'
            WHEN 5637145331 THEN 'HBFR'
            WHEN 5637146076 THEN 'HBPN'
            WHEN 5637146826 THEN 'HBCQ'
            WHEN 5637147577 THEN 'HBBV'
            WHEN 5637147578 THEN 'HBIN'
            WHEN 5637147579 THEN 'HBFM'
            WHEN 5637147580 THEN 'HBAQ'
            WHEN 5637149076 THEN 'HBIM'
            WHEN 5637149826 THEN 'HBDS'
            WHEN 5637150576 THEN 'HBCB'
            WHEN 5637154326 THEN 'HBSG'
            ELSE NULL
        END AS entity_code,
        date_format(gje.accountingdate, 'yyyy-MM') AS ym,
        gjae.accountingcurrencyamount AS accountingcurrencyamount,
        gjae.reportingcurrencyamount  AS reportingcurrencyamount
    FROM hb_catalog.db_bronze_d365.generaljournalaccountentry gjae
    JOIN hb_catalog.db_bronze_d365.generaljournalentry gje
        ON gje.recid = gjae.generaljournalentry
    JOIN hb_catalog.db_bronze_d365.mainaccount ma
        ON ma.recid = gjae.mainaccount
    WHERE COALESCE(gjae.IsDelete, false) = false
      AND COALESCE(gje.IsDelete, false)  = false
      AND gje.accountingdate >= {{RANGE_START}}
      AND gje.accountingdate <  {{RANGE_END_EXCLUSIVE}}
      AND (
            CAST(ma.mainaccountid AS BIGINT) BETWEEN 1000000 AND 3999999
            OR CAST(ma.mainaccountid AS BIGINT) >= 4000000
          )
),
grouped AS (
    SELECT
        entity_code,
        mainaccountid,
        MAX(mainaccountname) AS mainaccountname,
        ym,
        SUM(CASE WHEN accountingcurrencyamount > 0 THEN accountingcurrencyamount ELSE 0 END) AS debit_acc,
        SUM(CASE WHEN accountingcurrencyamount < 0 THEN -accountingcurrencyamount ELSE 0 END) AS credit_acc,
        SUM(CASE WHEN reportingcurrencyamount > 0 THEN reportingcurrencyamount ELSE 0 END) AS debit_rep,
        SUM(CASE WHEN reportingcurrencyamount < 0 THEN -reportingcurrencyamount ELSE 0 END) AS credit_rep
    FROM filtered
    WHERE entity_code IS NOT NULL
    GROUP BY entity_code, mainaccountid, ym
),
numbered AS (
    SELECT
        ROW_NUMBER() OVER (ORDER BY entity_code, mainaccountid, ym) AS rn,
        grouped.*
    FROM grouped
)
SELECT * FROM numbered
WHERE rn BETWEEN {{PAGE_START}} AND {{PAGE_END}}
ORDER BY rn;
