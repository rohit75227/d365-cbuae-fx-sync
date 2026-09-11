-- ============================================================================
-- Customer Balance: monthly movement per (legal entity, customer account) --
-- Databricks SQL (hb_catalog.db_bronze_d365)
-- ============================================================================
-- Feeds the "Customer Balance" tab's Accounting & Reporting view (the
-- "customer" collection). Mirrors sql/vendor_balance.sql exactly, using the
-- AR subledger (custtrans/custtable) instead of AP (vendtrans/vendtable) --
-- see that file's header for why each rule exists (dataareaid-based entity
-- attribution, no-KY exclusion, dirpartytable name lookup, cumulative
-- since inception with no fiscal-year reset).
--
-- Grain: one row per (legal_entity, customer_account, ym). Paginate with
-- the ROW_NUMBER() pattern (12,288-row cap) -- ~6,400 (entity, account, ym)
-- combinations across all of history as of 2026-09-10, comfortably under
-- one page, but paginated the same way as vendor for consistency.
--
-- Substitution tokens (replaced by hand or a render script):
--   {{RANGE_START}} / {{RANGE_END_EXCLUSIVE}}, {{PAGE_START}} / {{PAGE_END}}
-- ============================================================================

WITH filtered AS (
    SELECT
        UPPER(ct.dataareaid)         AS legal_entity,
        ct.accountnum                AS customer_account,
        dp.name                      AS customer_name,
        cd.custgroup                 AS customer_group,
        date_format(ct.transdate, 'yyyy-MM') AS ym,
        ct.amountmst                 AS amount_acc,
        ct.reportingcurrencyamount   AS amount_rep
    FROM hb_catalog.db_bronze_d365.custtrans ct
    JOIN hb_catalog.db_bronze_d365.custtable cd
        ON cd.accountnum = ct.accountnum AND cd.dataareaid = ct.dataareaid
    LEFT JOIN hb_catalog.db_bronze_d365.dirpartytable dp
        ON dp.recid = cd.party
    WHERE COALESCE(ct.IsDelete, false) = false
      AND LOWER(ct.dataareaid) NOT LIKE 'ky%'
      AND ct.transdate >= {{RANGE_START}}
      AND ct.transdate <  {{RANGE_END_EXCLUSIVE}}
),
grouped AS (
    SELECT
        legal_entity,
        customer_account,
        MAX(customer_name)  AS customer_name,
        MAX(customer_group) AS customer_group,
        ym,
        SUM(CASE WHEN amount_acc > 0 THEN amount_acc ELSE 0 END) AS debit_acc,
        SUM(CASE WHEN amount_acc < 0 THEN -amount_acc ELSE 0 END) AS credit_acc,
        SUM(CASE WHEN amount_rep > 0 THEN amount_rep ELSE 0 END) AS debit_rep,
        SUM(CASE WHEN amount_rep < 0 THEN -amount_rep ELSE 0 END) AS credit_rep
    FROM filtered
    GROUP BY legal_entity, customer_account, ym
),
numbered AS (
    SELECT
        ROW_NUMBER() OVER (ORDER BY legal_entity, customer_account, ym) AS rn,
        grouped.*
    FROM grouped
)
SELECT * FROM numbered
WHERE rn BETWEEN {{PAGE_START}} AND {{PAGE_END}}
ORDER BY rn;
