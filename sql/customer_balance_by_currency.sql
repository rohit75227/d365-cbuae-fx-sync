-- ============================================================================
-- Customer Balance by transaction currency: monthly movement per (legal
-- entity, customer account, transaction currency) -- Databricks SQL
-- (hb_catalog.db_bronze_d365)
-- ============================================================================
-- Feeds the "Customer Balance" tab's Transaction Currency view. Mirrors
-- sql/vendor_balance_by_currency.sql exactly, using the AR subledger
-- (custtrans/custtable) instead of AP -- see that file's header for why
-- each rule exists.
--
-- Grain: one row per (legal_entity, customer_account, currency, ym).
-- Paginate with the ROW_NUMBER() pattern (12,288-row cap).
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
        COALESCE(ct.currencycode, '???') AS txn_ccy,
        date_format(ct.transdate, 'yyyy-MM') AS ym,
        ct.amountcur                 AS amount_txn
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
        txn_ccy,
        ym,
        SUM(CASE WHEN amount_txn > 0 THEN amount_txn ELSE 0 END) AS debit_txn,
        SUM(CASE WHEN amount_txn < 0 THEN -amount_txn ELSE 0 END) AS credit_txn
    FROM filtered
    GROUP BY legal_entity, customer_account, txn_ccy, ym
),
numbered AS (
    SELECT
        ROW_NUMBER() OVER (ORDER BY legal_entity, customer_account, txn_ccy, ym) AS rn,
        grouped.*
    FROM grouped
)
SELECT * FROM numbered
WHERE rn BETWEEN {{PAGE_START}} AND {{PAGE_END}}
ORDER BY rn;
