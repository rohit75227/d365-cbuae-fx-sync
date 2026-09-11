-- ============================================================================
-- Vendor Balance by transaction currency: monthly movement per (legal
-- entity, vendor account, transaction currency) -- Databricks SQL
-- (hb_catalog.db_bronze_d365)
-- ============================================================================
-- Feeds the "Vendor Balance" tab's Transaction Currency view (the "vendor"
-- collection's currency-shards, one row per vendor + original posting
-- currency). Same source, entity mapping, and no-CLG-analog rules as
-- sql/vendor_balance.sql -- see that file's header for why each rule
-- exists. Grain here adds vendtrans.currencycode to the group-by.
--
-- amountcur is the RAW amount actually posted in that row's own
-- currencycode (not converted), mirroring how monthly_movement_by_currency.sql
-- carries transactioncurrencyamount for the GL-based tabs.
--
-- The vendtable join is case-INSENSITIVE on dataareaid -- see
-- sql/vendor_balance.sql's header for why (vendtable.dataareaid is stored
-- mixed-case for many vendors; vendtrans.dataareaid is always lowercase).
--
-- Grain: one row per (legal_entity, vendor_account, currency, ym). Paginate
-- with the ROW_NUMBER() pattern (12,288-row cap).
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
        COALESCE(vt.currencycode, '???') AS txn_ccy,
        date_format(vt.transdate, 'yyyy-MM') AS ym,
        vt.amountcur                 AS amount_txn
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
        txn_ccy,
        ym,
        SUM(CASE WHEN amount_txn > 0 THEN amount_txn ELSE 0 END) AS debit_txn,
        SUM(CASE WHEN amount_txn < 0 THEN -amount_txn ELSE 0 END) AS credit_txn
    FROM filtered
    GROUP BY legal_entity, vendor_account, txn_ccy, ym
),
numbered AS (
    SELECT
        ROW_NUMBER() OVER (ORDER BY legal_entity, vendor_account, txn_ccy, ym) AS rn,
        grouped.*
    FROM grouped
)
SELECT * FROM numbered
WHERE rn BETWEEN {{PAGE_START}} AND {{PAGE_END}}
ORDER BY rn;
