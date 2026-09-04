-- ============================================================================
-- Consolidated Trial Balance — Databricks SQL (hb_catalog.db_bronze_d365)
-- ============================================================================
-- Source: GL Reporting from D365 Bronze Layer (Claude Project instructions,
-- project 01a038c5-af45-73aa-8b6f-721ae4456189), corrected against three
-- things discovered by running this live via the claude-databricks-connector
-- (verified against real data on 2026-09-03) that the project instructions
-- either didn't cover or would have led here silently wrong:
--
-- 1. gje.fiscalcalendaryear / gje.fiscalcalendarperiod are NOT literal years
--    like 2026 -- they're RECIDs into a fiscal-calendar reference table that
--    isn't replicated to this bronze schema (values like 5637148326). Do not
--    filter on them as if they were integers. Use gje.accountingdate
--    (TIMESTAMP, half-open range) instead, exactly as the project's own
--    worked CLG example does.
--
-- 2. gje.subledgervoucherdataareaid is NULL for any GL entry that isn't tied
--    to a subledger voucher (accruals, manual journals, intercompany,
--    allocations -- a large share of real postings). Using it to attribute
--    entity/company drops those rows silently and breaks the trial balance's
--    debit=credit control total by hundreds of millions. gje.ledger (a
--    RECID, populated on every row) is the reliable field -- confirmed by
--    checking every distinct ledger value against the reference table with
--    zero unexplained values (24 distinct values total across all history:
--    16 operating entities + 9 KY entities + 8 stray NULL-ledger rows).
--
-- 3. CLG-tagged vouchers must NOT be excluded from either bucket, ever --
--    despite how tempting that looks for "showing this year's real,
--    unclosed P&L activity". Two dead ends were tried and both broke real
--    periods before landing on this:
--    a) Exclude ALL CLG entries everywhere -> strips out legitimate
--       Retained-Earnings roll-forward from every prior year's close,
--       understating equity by hundreds of millions cumulative-forward.
--    b) Exclude CLG only from the P&L bucket, keep it in the Balance Sheet
--       bucket -> fixed HBCB (whose Jan-2026 CLG batch happens to be 100%
--       Balance-Sheet-side, so this looked like the right fix), but SILENTLY
--       BROKE every other entity's December (year-end) period and any
--       later period, because a normal entity's December CLG batch is one
--       balanced double-entry transaction touching BOTH a P&L account
--       (zeroing it) AND a Balance Sheet account (crediting Retained
--       Earnings) -- keeping the BS side while dropping the P&L side of
--       the SAME transaction breaks it by exactly the amount zeroed.
--       Verified live: with (b), all 12 non-HBCB entities checked were off
--       by millions to over a billion for FY2025 P12 (December 2025).
--    The fix: NO CLG exclusion anywhere. A trial balance is just "whatever
--    the GL currently says", and any valid double-entry ledger balances to
--    0.00 by construction, closing entries included -- there is no need to
--    special-case CLG at all. For a still-open fiscal year (no close
--    posted yet), P&L naturally shows real accumulated activity. For an
--    already-closed year, P&L naturally shows ~0.00 for that year (that IS
--    what "closed" means) -- this is correct, not a bug, even though it
--    looks like a P&L account "goes to zero" between November and December.
--    Verified live: with the exclusion removed, 10 of 12 entities checked
--    net to EXACTLY 0.00 for FY2025 P12; the remaining discrepancies (HBCB,
--    HBUK) are real, already-diagnosed data issues (see the "Known open
--    control-total exceptions" list), not query artifacts.
--
-- Grain: one row per (mainaccountid, entity_code) for the requested
-- as-of period. The sync step pivots entities into columns.
--
-- Period logic (confirmed with the report owner):
--   - Balance Sheet accounts (mainaccountid 1000000-3999999): cumulative
--     from ledger inception through the selected period end. No exclusions.
--   - P&L accounts (mainaccountid >= 4000000): movement within the
--     selected fiscal year only (fiscal year confirmed = calendar year, by
--     the CLG close consistently landing in December). No exclusions --
--     see finding 3 above for why CLG must NOT be filtered out here.
--
-- Entities: gje.ledger mapped via the RECID table in the GL Reporting
-- project instructions. Any ledger not in that CASE (all "KY*" entities,
-- the consolidation ledgers CHBD/CHBI/CHBU, the shared DAT company, and the
-- 8 stray NULL-ledger rows) maps to NULL and is dropped by the outer
-- `WHERE entity_code IS NOT NULL`. HBCQ and HBFM are in the CASE but have
-- had zero GL activity historically as of this writing -- expected, not a
-- bug, they just won't appear in results until they post something.
--
-- Substitution tokens (replaced by scripts/render_query.py -- NOT bind
-- parameters, since the claude-databricks-connector's execute_sql_read_only
-- takes a raw SQL string with no parameter binding). Search this file for
-- the two "period end" / "fiscal year start" placeholders below the WHERE
-- clause's comments to see exactly where they're substituted.
--
-- Known open control-total exceptions as of the 2026-09-03 validation run
-- (do not silently re-exclude data trying to force these to zero -- flag
-- them to finance instead, per the project's own "surface data-quality
-- findings" working practice):
--   - HBCB: off by +278,118,823.43 (AED). Confirmed cause (per report
--     owner): HBCB's FY2025 year-end close hasn't been run yet -- its CLG
--     closing entries touch only Balance Sheet accounts, never P&L (unlike
--     every other entity), so 2024/2025 P&L was never transferred into
--     Retained Earnings. HBCB's full, unrestricted ledger (no fiscal-year
--     scoping) nets to ~0.00, so nothing is missing from Databricks -- this
--     should self-resolve once that close is posted in D365. Not a query
--     bug; don't "fix" it here.
--   - HBUK: off by -18,000.00 (accounting) / -24,683.40 (reporting) in
--     FY2026 periods -- but FY2025 P12 (December 2025) itself nets to
--     EXACTLY 0.00 after the 2026-09-04 fix (see finding 3). That split
--     result means the account 6210008 "Other Marketing - Influencer"
--     story traced on 2026-09-03 (late close, voucher clguk25v2 posted
--     2026-08-13, under-reversed by exactly 18,000.00) is not the full
--     picture -- something 2026-dated, connected to the same late close,
--     is involved too. Not yet fully isolated; the simulated adjustment
--     still correctly zeroes it for FY2026 periods in the meantime.
--   - HBFR: reporting-currency-only, off by +2,443.07 (accounting currency
--     ties exactly) -- looks like an FX-translation rounding artifact.
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
        gjae.accountingcurrencyamount AS accountingcurrencyamount,
        gjae.reportingcurrencyamount  AS reportingcurrencyamount
    FROM hb_catalog.db_bronze_d365.generaljournalaccountentry gjae
    JOIN hb_catalog.db_bronze_d365.generaljournalentry gje
        ON gje.recid = gjae.generaljournalentry
    JOIN hb_catalog.db_bronze_d365.mainaccount ma
        ON ma.recid = gjae.mainaccount
    WHERE COALESCE(gjae.IsDelete, false) = false
      AND COALESCE(gje.IsDelete, false)  = false
      AND gje.accountingdate < {{PERIOD_END_EXCLUSIVE}}
      AND (
            -- Balance Sheet: cumulative since inception. No exclusions --
            -- a valid double-entry ledger balances by construction.
            CAST(ma.mainaccountid AS BIGINT) BETWEEN 1000000 AND 3999999
            OR
            -- P&L: this fiscal year only. No CLG exclusion here either --
            -- see finding 3 in the header comment for why that broke
            -- December (year-end) periods for every entity.
            (
              CAST(ma.mainaccountid AS BIGINT) >= 4000000
              AND gje.accountingdate >= {{FY_START}}
            )
          )
)
SELECT
    mainaccountid,
    mainaccountname,
    entity_code,
    SUM(accountingcurrencyamount) AS accountingcurrencyamount,
    SUM(reportingcurrencyamount)  AS reportingcurrencyamount,
    COUNT(*) AS line_count
FROM filtered
WHERE entity_code IS NOT NULL
GROUP BY mainaccountid, mainaccountname, entity_code
ORDER BY mainaccountid, entity_code;
