-- ============================================================================
-- Monthly Dr/Cr movement, closing/opening-period aware — Databricks SQL
-- (hb_catalog.db_bronze_d365)
-- ============================================================================
-- Supersedes sql/monthly_movement.sql. That version grouped purely by
-- calendar accountingdate month, which silently merged D365's special
-- "Closing" and "Opening" fiscal periods into the regular calendar month
-- they happen to share a date with (both are dated the very last/first day
-- of a fiscal year). This is wrong:
--
--   - D365 posts a "Closing" period entry dated 31-Dec that, for THIS
--     dataset, reverses close to the ENTIRE YEAR's net movement for every
--     account it touches (not just P&L) -- confirmed by comparing our
--     query's fiscalcalendarperiod against a live D365-generated Trial
--     Balance export for HBDM Dec 2025: D365's own period-12 report
--     EXCLUDES this closing entry entirely (its Dec 2025 closing balances
--     match our numbers only once the closing-period rows are removed).
--   - D365 then posts an "Opening" period entry dated 1-Jan of the
--     following year that re-establishes the true carried-forward balance
--     for Balance Sheet accounts (confirmed: the Jan-1 entry's amount
--     exactly cancels a bank account's closing-period reversal in one
--     verified case; other accounts, e.g. Retained Earnings, receive a
--     new value on that date rather than the closing reversed).
--
-- A Closing/Opening period pair is identified generically, per (ledger,
-- calendar year), as: among the fiscalcalendarperiod values whose latest
-- accountingdate is 12-31 of that year, the one with fewer distinct
-- accountingdates than the "regular" period-12 value is the Closing
-- period (same test applied to 1-Jan of the following year would find the
-- Opening period, but Opening entries need no special handling -- they
-- already fall within their own year's regular calendar month, e.g.
-- 2026-01, exactly where they belong).
--
-- Fix applied to the Closing period's rows only:
--   - Balance Sheet accounts (1,000,000-3,999,999): re-bucketed into
--     January of the FOLLOWING year, so they are excluded from the
--     closing year's own December cumulative balance (matching D365's own
--     period-12 report) but still counted from the next period onward
--     (matching the real, continuous balance -- the entry is real money
--     movement, just administratively dated to a period D365 excludes
--     from its own year's report).
--   - P&L accounts (>= 4,000,000): dropped entirely. Our own build already
--     resets P&L to zero every January; the Closing period's job for a
--     P&L account is exactly that reset, so including it would double it.
--
-- Same entity mapping, IsDelete, and account-range rules as
-- consolidated_trial_balance.sql. Grain: one row per (entity_code,
-- mainaccountid, ym), same shape as monthly_movement.sql, so it's a
-- drop-in replacement for scripts/build_series_from_movement.py.
--
-- Substitution tokens (replaced by hand or a render script):
--   {{RANGE_START}}            -- inclusive, e.g. TIMESTAMP'2019-01-01T00:00:00Z'
--   {{RANGE_END_EXCLUSIVE}}    -- exclusive, e.g. TIMESTAMP'2026-09-01T00:00:00Z'
--   {{PAGE_START}} / {{PAGE_END}} -- inclusive rn bounds for one page
-- ============================================================================

WITH filtered AS (
    SELECT
        ma.mainaccountid AS mainaccountid,
        ma.name          AS mainaccountname,
        gje.ledger       AS ledger,
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
        gje.accountingdate AS accountingdate,
        gje.fiscalcalendarperiod AS fcp,
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
period_dates AS (
    SELECT ledger, fcp,
           date_format(accountingdate, 'yyyy') AS cal_year,
           MAX(accountingdate) AS mx,
           COUNT(DISTINCT accountingdate) AS ndates
    FROM filtered
    GROUP BY ledger, fcp, date_format(accountingdate, 'yyyy')
),
dec31_periods AS (
    SELECT ledger, fcp, cal_year, ndates
    FROM period_dates
    WHERE date_format(mx, 'MM-dd') = '12-31'
),
ranked AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY ledger, cal_year ORDER BY ndates DESC) AS rn
    FROM dec31_periods
),
closing_periods AS (
    SELECT ledger, cal_year, fcp
    FROM ranked
    WHERE rn > 1
),
tagged AS (
    SELECT
        f.entity_code,
        f.mainaccountid,
        f.mainaccountname,
        f.accountingcurrencyamount,
        f.reportingcurrencyamount,
        CASE
            WHEN cp.fcp IS NOT NULL AND CAST(f.mainaccountid AS BIGINT) < 4000000
                THEN CONCAT(CAST(YEAR(f.accountingdate) + 1 AS STRING), '-01')
            WHEN cp.fcp IS NOT NULL
                THEN NULL
            ELSE date_format(f.accountingdate, 'yyyy-MM')
        END AS ym
    FROM filtered f
    LEFT JOIN closing_periods cp
        ON cp.ledger = f.ledger
       AND cp.cal_year = date_format(f.accountingdate, 'yyyy')
       AND cp.fcp = f.fcp
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
    FROM tagged
    WHERE entity_code IS NOT NULL AND ym IS NOT NULL
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
