from django.db import migrations

FORWARD = r"""
-- Money lost to stock that will never be sold: expired units still on the shelf
-- plus everything written off. Grafana's "Loss from expiry" panels read this.
CREATE OR REPLACE VIEW v_stock_loss AS
SELECT 'ON_SHELF_EXPIRED'::text AS kind, b.expiry_date::timestamptz AS happened_at, c.name AS category,
       m.name || CASE WHEN m.strength <> '' THEN ' ' || m.strength ELSE '' END AS medicine,
       b.quantity_available AS quantity, b.quantity_available * b.cost_price AS loss_value
  FROM inventory_batch b
  JOIN inventory_medicine m ON m.id = b.medicine_id
  JOIN inventory_category c ON c.id = m.category_id
 WHERE b.expiry_date < pharma_today() AND b.quantity_available > 0
UNION ALL
SELECT 'WRITTEN_OFF', w.created_at, c.name,
       m.name || CASE WHEN m.strength <> '' THEN ' ' || m.strength ELSE '' END,
       w.quantity, w.cost_value
  FROM inventory_stockwriteoff w
  JOIN inventory_batch b ON b.id = w.batch_id
  JOIN inventory_medicine m ON m.id = b.medicine_id
  JOIN inventory_category c ON c.id = m.category_id;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'grafana_reader') THEN
        GRANT SELECT ON ALL TABLES IN SCHEMA public TO grafana_reader;
    END IF;
END $$;
"""


class Migration(migrations.Migration):
    dependencies = [("inventory", "0003_stock_writeoff")]
    operations = [migrations.RunSQL(FORWARD, "DROP VIEW IF EXISTS v_stock_loss;")]
