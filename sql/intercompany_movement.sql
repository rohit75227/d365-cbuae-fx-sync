-- ============================================================================
-- Intercompany Reconciliation: monthly Dr/Cr movement by account --
-- Databricks SQL (hb_catalog.db_bronze_d365)
-- ============================================================================
-- Feeds the "Intercompany Reconciliation" tab: intercompany receivable
-- accounts (mainaccountid 1122001-1122999) and intercompany payable
-- accounts (mainaccountid 2112001-2112999), entities in columns, one row
-- per counterparty account.
--
-- Same entity mapping, IsDelete, and no-CLG-exclusion rules as
-- consolidated_trial_balance.sql / monthly_movement.sql -- see those files'
-- header comments for why. Both account ranges are pure Balance Sheet
-- (cumulative-since-inception, no fiscal-year reset), so -- unlike
-- consolidated_trial_balance.sql -- there is no P&L bucket and no
-- FY_START token needed here: this is monthly movement only, forward-summed
-- into a cumulative balance client-side (scripts/build_intercompany_periods.py),
-- exactly like monthly_movement.sql feeds the Company TB tab's Opening/
-- Closing via the already-published tb/<period> baseline -- except here
-- there IS no separately-published cumulative baseline, so the forward-sum
-- starts from zero at inception rather than from a stored prior balance.
--
-- Kayali is a related but SEPARATE brand/legal group -- its intercompany
-- balances are out of scope for this reconciliation (confirmed with report
-- owner, 2026-09-07). Excluded by name (LOWER(ma.name) LIKE '%kayali%'),
-- not by a sub-range of mainaccountid, because Kayali-counterparty accounts
-- are interleaved with in-scope accounts within both ranges (e.g. 1122123
-- "Accounts Receivable - Kayali DMCC" sits between 1122122 and 1122124,
-- both in-scope).
--
-- Grain: one row per (entity_code, mainaccountid, ym). ~5,600 rows across
-- 2019-01 through the present as of 2026-09-07 -- comfortably under the
-- 12,288-row single-page cap, no ROW_NUMBER() pagination needed.
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
      AND (
            CAST(ma.mainaccountid AS BIGINT) BETWEEN 1122001 AND 1122999
            OR CAST(ma.mainaccountid AS BIGINT) BETWEEN 2112001 AND 2112999
          )
      AND LOWER(ma.name) NOT LIKE '%kayali%'
)
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
ORDER BY mainaccountid, entity_code, ym;
