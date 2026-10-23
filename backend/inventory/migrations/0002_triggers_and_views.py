"""
Database-level logic for the DBMS part of the project.

1. pharma_today()        - "today" in the pharmacy's time zone, used by every view.
2. trg_sale_item_stock   - trigger that keeps batch stock correct:
                             INSERT sale item -> check expiry & stock, then decrement
                             DELETE sale item -> put units back (bill cancelled)
                             UPDATE sale item -> rejected (bills are immutable)
3. Reporting views used by both the API and Grafana:
     v_medicine_stock   - stock, value and low-stock flag per medicine
     v_batch_expiry     - every batch with days-to-expiry and a status bucket
     v_sales_detail     - one row per sold line with category and profit
     v_daily_sales      - revenue / bills per day
4. Grants SELECT to the read-only `grafana_reader` role (created by db/init).
"""
from django.db import migrations

FORWARD = r"""
CREATE OR REPLACE FUNCTION pharma_today() RETURNS date
LANGUAGE sql STABLE AS $$ SELECT (now() AT TIME ZONE 'Asia/Kolkata')::date $$;

-- ------------------------------------------------------------------ trigger
CREATE OR REPLACE FUNCTION fn_sale_item_stock() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_expiry     date;
    v_available  integer;
    v_sale_date  date;
BEGIN
    IF TG_OP = 'INSERT' THEN
        SELECT expiry_date, quantity_available INTO v_expiry, v_available
          FROM inventory_batch WHERE id = NEW.batch_id FOR UPDATE;

        SELECT (created_at AT TIME ZONE 'Asia/Kolkata')::date INTO v_sale_date
          FROM inventory_sale WHERE id = NEW.sale_id;

        IF v_expiry < v_sale_date THEN
            RAISE EXCEPTION 'Batch % expired on % and cannot be sold', NEW.batch_id, v_expiry
                USING ERRCODE = 'check_violation';
        END IF;
        IF v_available < NEW.quantity THEN
            RAISE EXCEPTION 'Insufficient stock in batch % (available %, requested %)',
                NEW.batch_id, v_available, NEW.quantity
                USING ERRCODE = 'check_violation';
        END IF;

        UPDATE inventory_batch
           SET quantity_available = quantity_available - NEW.quantity
         WHERE id = NEW.batch_id;
        RETURN NEW;

    ELSIF TG_OP = 'DELETE' THEN
        UPDATE inventory_batch
           SET quantity_available = quantity_available + OLD.quantity
         WHERE id = OLD.batch_id;
        RETURN OLD;

    ELSE  -- UPDATE
        RAISE EXCEPTION 'Sale items cannot be modified; cancel the bill instead'
            USING ERRCODE = 'restrict_violation';
    END IF;
END;
$$;

CREATE TRIGGER trg_sale_item_stock
AFTER INSERT OR UPDATE OR DELETE ON inventory_saleitem
FOR EACH ROW EXECUTE FUNCTION fn_sale_item_stock();

-- ------------------------------------------------------------------ views
CREATE OR REPLACE VIEW v_medicine_stock AS
SELECT
    m.id                                   AS medicine_id,
    m.name,
    m.strength,
    m.brand,
    m.name || CASE WHEN m.strength <> '' THEN ' ' || m.strength ELSE '' END AS display_name,
    c.name                                 AS category,
    m.unit_price,
    m.reorder_level,
    m.requires_prescription,
    m.is_active,
    COALESCE(SUM(b.quantity_available) FILTER (WHERE b.expiry_date >= pharma_today()), 0)::int AS stock,
    COALESCE(SUM(b.quantity_available * b.cost_price) FILTER (WHERE b.expiry_date >= pharma_today()), 0)
                                           AS stock_value,
    MIN(b.expiry_date) FILTER (WHERE b.expiry_date >= pharma_today() AND b.quantity_available > 0)
                                           AS nearest_expiry,
    COALESCE(SUM(b.quantity_available) FILTER (WHERE b.expiry_date >= pharma_today()), 0)
        < m.reorder_level                  AS is_low_stock
FROM inventory_medicine m
JOIN inventory_category c ON c.id = m.category_id
LEFT JOIN inventory_batch b ON b.medicine_id = m.id
GROUP BY m.id, c.name;

CREATE OR REPLACE VIEW v_batch_expiry AS
SELECT
    b.id                                   AS batch_id,
    b.medicine_id,
    m.name || CASE WHEN m.strength <> '' THEN ' ' || m.strength ELSE '' END AS medicine,
    c.name                                 AS category,
    s.name                                 AS supplier,
    b.batch_number,
    b.quantity_available,
    b.cost_price,
    b.quantity_available * b.cost_price    AS stock_value,
    b.mfg_date,
    b.expiry_date,
    (b.expiry_date - pharma_today())       AS days_to_expiry,
    CASE
        WHEN b.expiry_date <  pharma_today()      THEN 'EXPIRED'
        WHEN b.expiry_date <= pharma_today() + 30 THEN 'CRITICAL'
        WHEN b.expiry_date <= pharma_today() + 90 THEN 'WARNING'
        ELSE 'OK'
    END                                    AS status
FROM inventory_batch b
JOIN inventory_medicine m ON m.id = b.medicine_id
JOIN inventory_category c ON c.id = m.category_id
JOIN inventory_supplier s ON s.id = b.supplier_id;

CREATE OR REPLACE VIEW v_sales_detail AS
SELECT
    si.id                                  AS sale_item_id,
    sa.id                                  AS sale_id,
    sa.invoice_number,
    sa.created_at                          AS sold_at,
    sa.payment_method,
    si.medicine_id,
    m.name || CASE WHEN m.strength <> '' THEN ' ' || m.strength ELSE '' END AS medicine,
    c.name                                 AS category,
    si.quantity,
    si.unit_price,
    si.line_total,
    si.line_total - si.quantity * b.cost_price AS gross_profit
FROM inventory_saleitem si
JOIN inventory_sale     sa ON sa.id = si.sale_id
JOIN inventory_batch    b  ON b.id  = si.batch_id
JOIN inventory_medicine m  ON m.id  = si.medicine_id
JOIN inventory_category c  ON c.id  = m.category_id;

CREATE OR REPLACE VIEW v_daily_sales AS
SELECT
    (created_at AT TIME ZONE 'Asia/Kolkata')::date AS day,
    COUNT(*)                               AS bills,
    SUM(total_amount)                      AS revenue,
    SUM(discount)                          AS discount,
    ROUND(AVG(total_amount), 2)            AS avg_bill
FROM inventory_sale
GROUP BY 1;

-- ------------------------------------------------------------------ grants
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'grafana_reader') THEN
        GRANT USAGE ON SCHEMA public TO grafana_reader;
        GRANT SELECT ON ALL TABLES IN SCHEMA public TO grafana_reader;
    END IF;
END $$;
"""

REVERSE = r"""
DROP VIEW IF EXISTS v_daily_sales;
DROP VIEW IF EXISTS v_sales_detail;
DROP VIEW IF EXISTS v_batch_expiry;
DROP VIEW IF EXISTS v_medicine_stock;
DROP TRIGGER IF EXISTS trg_sale_item_stock ON inventory_saleitem;
DROP FUNCTION IF EXISTS fn_sale_item_stock();
DROP FUNCTION IF EXISTS pharma_today();
"""


class Migration(migrations.Migration):
    dependencies = [("inventory", "0001_initial")]
    operations = [migrations.RunSQL(FORWARD, REVERSE)]
