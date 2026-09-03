-- ============================================================================
-- Consolidated Trial Balance — Databricks SQL (hb_catalog.db_bronze_d365)
-- ============================================================================
-- Source: GL Reporting from D365 Bronze Layer (Claude Project instructions,
-- project 01a038c5-af45-73aa-8b6f-721ae4456189). Applies all four mandatory
-- rules from that project verbatim:
--   1. IsDelete is NULL, not false -> COALESCE(..., false) = false
--   2. subledgervoucherdataareaid is mixed case -> always UPPER()
--   3. CLG closing vouchers zero out full-year P&L -> excluded via LOWER() LIKE
--   4. Databricks connector caps results at 12,288 rows -> caller must check
--      the "truncated" flag on the statement result and paginate if needed
--      (unlikely to bite here since this is a GROUP BY down to
--      mainaccount x entity, but verify on first run against real volumes).
--
-- Grain: one row per (mainaccountid, entity_code) for the requested
-- fiscal year / period. The sync script pivots entities into columns.
--
-- Period logic (confirmed with the report owner):
--   - Balance Sheet accounts (mainaccountid 1000000-3999999): cumulative
--     from ledger inception through the selected fiscal year/period.
--   - P&L accounts (mainaccountid >= 4000000): movement within the
--     selected fiscal year only (Jan/period-1 through the selected period),
--     using gje.fiscalcalendaryear / gje.fiscalcalendarperiod rather than
--     calendar-date math, since those are the fields D365 already carries
--     and the fiscal calendar need not be a plain calendar year.
--
-- Entities: all legal entities EXCEPT any whose subledgervoucherdataareaid
-- contains "KY" (per project instructions: "exclude all entities which
-- contains KY").
--
-- Parameters (substituted by scripts/sync_trial_balance.py):
--   :fiscal_year  -- e.g. 2026
--   :period       -- e.g. 6  (selected period end, 1-12)
-- ============================================================================

WITH filtered AS (
    SELECT
        ma.mainaccountid                                       AS mainaccountid,
        ma.name                                                AS mainaccountname,
        UPPER(COALESCE(gje.subledgervoucherdataareaid, ''))    AS entity_code,
        gjae.accountingcurrencyamount                          AS accountingcurrencyamount,
        gjae.reportingcurrencyamount                           AS reportingcurrencyamount
    FROM hb_catalog.db_bronze_d365.generaljournalaccountentry gjae
    JOIN hb_catalog.db_bronze_d365.generaljournalentry gje
        ON gje.recid = gjae.generaljournalentry
    JOIN hb_catalog.db_bronze_d365.mainaccount ma
        ON ma.recid = gjae.mainaccount
    WHERE COALESCE(gjae.IsDelete, false) = false
      AND COALESCE(gje.IsDelete, false)  = false
      AND LOWER(COALESCE(gje.subledgervoucher, '')) NOT LIKE '%clg%'
      AND UPPER(COALESCE(gje.subledgervoucherdataareaid, '')) NOT LIKE '%KY%'
      AND (
            -- Balance Sheet: cumulative through the selected period, any fiscal year
            (
              CAST(ma.mainaccountid AS BIGINT) BETWEEN 1000000 AND 3999999
              AND (
                    gje.fiscalcalendaryear < :fiscal_year
                    OR (gje.fiscalcalendaryear = :fiscal_year AND gje.fiscalcalendarperiod <= :period)
                  )
            )
            OR
            -- P&L: movement within the selected fiscal year only, up to selected period
            (
              CAST(ma.mainaccountid AS BIGINT) >= 4000000
              AND gje.fiscalcalendaryear = :fiscal_year
              AND gje.fiscalcalendarperiod <= :period
            )
          )
)
SELECT
    mainaccountid,
    mainaccountname,
    entity_code,
    SUM(accountingcurrencyamount) AS accountingcurrencyamount,
    SUM(reportingcurrencyamount)  AS reportingcurrencyamount,
    COUNT(*)                      AS line_count
FROM filtered
GROUP BY mainaccountid, mainaccountname, entity_code
ORDER BY mainaccountid, entity_code;

-- ----------------------------------------------------------------------------
-- Control totals to run alongside every sync (per project working practice:
-- "verify before delivering" and "use the balance check"). A clean extract's
-- accountingcurrencyamount AND reportingcurrencyamount must each net to 0.00
-- across all accounts, per entity (debits = credits). Reporting currency
-- will only net to zero for entities that actually have a reporting currency
-- populated (see HBBV / HBFM note in the sync script).
-- ----------------------------------------------------------------------------
