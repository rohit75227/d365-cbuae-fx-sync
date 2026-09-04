-- ============================================================================
-- Monthly movement by transaction currency — Databricks SQL
-- (hb_catalog.db_bronze_d365)
-- ============================================================================
-- Feeds the "By Currency" view: the consolidated trial balance (accounting or
-- reporting currency) with the account's ORIGINAL POSTING (transaction)
-- currency as an extra row dimension, so one main account can show multiple
-- rows split by the currency each amount was actually posted in.
--
-- Same entity mapping, IsDelete, account-range, and no-CLG-exclusion rules as
-- consolidated_trial_balance.sql and monthly_movement.sql -- see those files'
-- header comments for why. Grain here adds transactioncurrencycode to the
-- group-by (mapped to '???' via COALESCE for the small number of rows where
-- it is NULL, so they still show up as an identifiable bucket rather than
-- being silently dropped).
--
-- Debit/credit split uses the SIGN of the amount, not `iscredit`, for the
-- same reason as monthly_movement.sql: it must reconcile with the
-- already-published, sign-based trial balance.
--
-- Grain: one row per (entity_code, mainaccountid, txn_ccy, ym). ~93,802 rows
-- across 2019-01 through 2026-09 (partial) as of 2026-09-04 -- paginate with
-- the ROW_NUMBER() pattern (12,288-row cap).
--
-- Substitution tokens (replaced by scripts/render_query.py):
--   {{RANGE_START}} / {{RANGE_END_EXCLUSIVE}}, {{PAGE_START}} / {{PAGE_END}}
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
        COALESCE(gjae.transactioncurrencycode, '???') AS txn_ccy,
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
        txn_ccy,
        SUM(CASE WHEN accountingcurrencyamount > 0 THEN accountingcurrencyamount ELSE 0 END) AS debit_acc,
        SUM(CASE WHEN accountingcurrencyamount < 0 THEN -accountingcurrencyamount ELSE 0 END) AS credit_acc,
        SUM(CASE WHEN reportingcurrencyamount > 0 THEN reportingcurrencyamount ELSE 0 END) AS debit_rep,
        SUM(CASE WHEN reportingcurrencyamount < 0 THEN -reportingcurrencyamount ELSE 0 END) AS credit_rep
    FROM filtered
    WHERE entity_code IS NOT NULL
    GROUP BY entity_code, mainaccountid, ym, txn_ccy
),
numbered AS (
    SELECT
        ROW_NUMBER() OVER (ORDER BY entity_code, mainaccountid, txn_ccy, ym) AS rn,
        grouped.*
    FROM grouped
)
SELECT * FROM numbered
WHERE rn BETWEEN {{PAGE_START}} AND {{PAGE_END}}
ORDER BY rn;
