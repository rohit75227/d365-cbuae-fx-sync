-- ============================================================================
-- Vendor Balance: monthly movement per (legal entity, vendor account) --
-- Databricks SQL (hb_catalog.db_bronze_d365)
-- ============================================================================
-- Feeds the "Vendor Balance" tab's Accounting & Reporting view (the
-- "vendor" collection). Balance Sheet / Accounts Payable in nature --
-- cumulative since ledger inception, no fiscal-year reset -- so this is
-- monthly movement only, forward-summed into a cumulative balance
-- client-side (scripts/build_vendor_balance_periods.py), exactly like
-- sql/intercompany_movement.sql feeds the Intercompany tab.
--
-- Source is the AP subledger (vendtrans), not the GL (generaljournalentry)
-- -- vendtrans.amountmst is the vendor's transaction amount in the
-- transacting company's own (accounting) currency, reportingcurrencyamount
-- is the same converted to USD. Entity attribution uses vendtrans.dataareaid
-- directly (the D365 company code, lowercase e.g. "hbdm") rather than a
-- ledger RECID join, since AP/AR subledger tables carry the company code
-- natively -- verified live: dataareaid values are exactly the 16 tracked
-- entities (lowercased) plus 8 "ky*" Kayali-related companies, mirroring
-- the "KY" exclusion already applied elsewhere in this report.
--
-- Vendor name comes from dirpartytable.name via vendtable.party (vendtable
-- itself has no name column) -- LEFT JOIN so a vendor whose master record
-- was later deleted/merged still keeps its transaction history and simply
-- shows a blank name rather than disappearing.
--
-- The vendtable join is case-INSENSITIVE on dataareaid: vendtrans.dataareaid
-- is always lowercase, but vendtable.dataareaid is stored mixed-case (e.g.
-- "HBDS") for a large share of vendor master records -- an exact-match join
-- silently dropped every transaction for those vendors (confirmed live:
-- 100% of HBDS/DSV001281's 184 transactions had zero matching vendtable
-- rows under an exact-match join, purely from case, even though the vendor
-- master record exists).
--
-- Grain: one row per (legal_entity, vendor_account, ym). Paginate with the
-- ROW_NUMBER() pattern (12,288-row cap) -- ~27,000 (entity, account, ym)
-- combinations across all of history as of 2026-09-10, so this needs
-- multiple pages.
--
-- Substitution tokens (replaced by hand or a render script):
--   {{RANGE_START}} / {{RANGE_END_EXCLUSIVE}}, {{PAGE_START}} / {{PAGE_END}}
-- ============================================================================

WITH filtered AS (
    SELECT
        UPPER(vt.dataareaid)         AS legal_entity,
        vt.accountnum                AS vendor_account,
        dp.name                      AS vendor_name,
        vd.vendgroup                 AS vendor_group,
        date_format(vt.transdate, 'yyyy-MM') AS ym,
        vt.amountmst                 AS amount_acc,
        vt.reportingcurrencyamount   AS amount_rep
    FROM hb_catalog.db_bronze_d365.vendtrans vt
    JOIN hb_catalog.db_bronze_d365.vendtable vd
        ON vd.accountnum = vt.accountnum AND LOWER(vd.dataareaid) = vt.dataareaid
    LEFT JOIN hb_catalog.db_bronze_d365.dirpartytable dp
        ON dp.recid = vd.party
    WHERE COALESCE(vt.IsDelete, false) = false
      AND LOWER(vt.dataareaid) NOT LIKE 'ky%'
      AND vt.transdate >= {{RANGE_START}}
      AND vt.transdate <  {{RANGE_END_EXCLUSIVE}}
),
grouped AS (
    SELECT
        legal_entity,
        vendor_account,
        MAX(vendor_name)  AS vendor_name,
        MAX(vendor_group) AS vendor_group,
        ym,
        SUM(CASE WHEN amount_acc > 0 THEN amount_acc ELSE 0 END) AS debit_acc,
        SUM(CASE WHEN amount_acc < 0 THEN -amount_acc ELSE 0 END) AS credit_acc,
        SUM(CASE WHEN amount_rep > 0 THEN amount_rep ELSE 0 END) AS debit_rep,
        SUM(CASE WHEN amount_rep < 0 THEN -amount_rep ELSE 0 END) AS credit_rep
    FROM filtered
    GROUP BY legal_entity, vendor_account, ym
),
numbered AS (
    SELECT
        ROW_NUMBER() OVER (ORDER BY legal_entity, vendor_account, ym) AS rn,
        grouped.*
    FROM grouped
)
SELECT * FROM numbered
WHERE rn BETWEEN {{PAGE_START}} AND {{PAGE_END}}
ORDER BY rn;
