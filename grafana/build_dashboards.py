#!/usr/bin/env python3
"""
Generates the three provisioned Grafana dashboards in grafana/dashboards/.

Editing panels in the Grafana UI works too (allowUiUpdates is on), but keeping
them as code means they are version-controlled and reviewable. Re-run with:

    python grafana/build_dashboards.py
"""
import json
from pathlib import Path

OUT = Path(__file__).parent / "dashboards"
PG = {"type": "grafana-postgresql-datasource", "uid": "pharmatrack-pg"}
PROM = {"type": "prometheus", "uid": "prometheus"}

GREEN, DEEP, AMBER, RED, BLUE, GREY = "#2e7d5b", "#0f4c3a", "#d98a00", "#c4302b", "#3b6fd1", "#8a9a93"
IST_DAY = "(date_trunc('day', {col} AT TIME ZONE 'Asia/Kolkata') AT TIME ZONE 'Asia/Kolkata')"


class Board:
    def __init__(self, uid, title, description, tags, time_from="now-30d", refresh="1m"):
        self.uid, self.title, self.description, self.tags = uid, title, description, tags
        self.time_from, self.refresh = time_from, refresh
        self.panels, self.variables = [], []
        self.x = self.y = self.row_h = 0
        self.next_id = 1

    # -------------------------------------------------- layout
    def place(self, w, h):
        if self.x + w > 24:
            self.x, self.y = 0, self.y + self.row_h
            self.row_h = 0
        pos = {"x": self.x, "y": self.y, "w": w, "h": h}
        self.x += w
        self.row_h = max(self.row_h, h)
        return pos

    def newline(self):
        if self.x:
            self.x, self.y, self.row_h = 0, self.y + self.row_h, 0

    def section(self, title):
        self.newline()
        self._add({"type": "row", "title": title, "collapsed": False, "panels": [], "gridPos": self.place(24, 1)})
        self.newline()

    def _add(self, panel):
        panel["id"] = self.next_id
        self.next_id += 1
        self.panels.append(panel)
        return panel

    # -------------------------------------------------- targets
    @staticmethod
    def sql(query, fmt="table", ref="A"):
        return {"refId": ref, "datasource": PG, "editorMode": "code", "format": fmt, "rawQuery": True, "rawSql": query.strip()}

    @staticmethod
    def prom(expr, legend="", ref="A", instant=False):
        t = {"refId": ref, "datasource": PROM, "editorMode": "code", "expr": expr, "legendFormat": legend or "__auto",
             "range": not instant, "instant": instant}
        return t

    # -------------------------------------------------- panels
    def stat(self, title, target, unit="none", w=4, h=4, decimals=0, steps=None, description="", color_mode="value"):
        steps = steps or [{"color": DEEP, "value": None}]
        return self._add({
            "type": "stat", "title": title, "description": description, "gridPos": self.place(w, h),
            "datasource": target["datasource"], "targets": [target],
            "fieldConfig": {"defaults": {"unit": unit, "decimals": decimals, "color": {"mode": "thresholds"},
                                         "thresholds": {"mode": "absolute", "steps": steps}}, "overrides": []},
            "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                        "colorMode": color_mode, "graphMode": "none", "textMode": "value", "justifyMode": "auto",
                        "orientation": "auto", "wideLayout": True},
        })

    def timeseries(self, title, targets, unit="none", w=12, h=8, bars=False, stack=False, colors=None,
                   description="", decimals=None, overrides=None):
        defaults = {
            "unit": unit, "color": {"mode": "palette-classic"},
            "custom": {"drawStyle": "bars" if bars else "line", "lineWidth": 2, "fillOpacity": 70 if bars else 12,
                       "barAlignment": 0, "pointSize": 4, "showPoints": "never", "spanNulls": True,
                       "gradientMode": "none", "axisBorderShow": False,
                       "stacking": {"mode": "normal" if stack else "none", "group": "A"}},
        }
        if decimals is not None:
            defaults["decimals"] = decimals
        ov = list(overrides or [])
        for name, color in (colors or {}).items():
            ov.append({"matcher": {"id": "byName", "options": name},
                       "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": color}}]})
        return self._add({
            "type": "timeseries", "title": title, "description": description, "gridPos": self.place(w, h),
            "datasource": targets[0]["datasource"], "targets": targets,
            "fieldConfig": {"defaults": defaults, "overrides": ov},
            "options": {"legend": {"showLegend": True, "displayMode": "list", "placement": "bottom"},
                        "tooltip": {"mode": "multi", "sort": "desc"}},
        })

    def barchart(self, title, target, x_field, unit="none", w=12, h=8, color=GREEN, description="", horizontal=False):
        return self._add({
            "type": "barchart", "title": title, "description": description, "gridPos": self.place(w, h),
            "datasource": target["datasource"], "targets": [target],
            "fieldConfig": {"defaults": {"unit": unit, "color": {"mode": "fixed", "fixedColor": color},
                                         "custom": {"fillOpacity": 85, "lineWidth": 0, "gradientMode": "none",
                                                    "axisBorderShow": False}}, "overrides": []},
            "options": {"xField": x_field, "orientation": "horizontal" if horizontal else "vertical",
                        "showValue": "auto", "barWidth": 0.8, "groupWidth": 0.7, "stacking": "none",
                        "xTickLabelRotation": 0, "xTickLabelSpacing": 0,
                        "legend": {"showLegend": False, "displayMode": "list", "placement": "bottom"},
                        "tooltip": {"mode": "single", "sort": "none"}},
        })

    def pie(self, title, target, unit="none", w=8, h=8, description=""):
        return self._add({
            "type": "piechart", "title": title, "description": description, "gridPos": self.place(w, h),
            "datasource": target["datasource"], "targets": [target],
            "fieldConfig": {"defaults": {"unit": unit, "decimals": 0, "color": {"mode": "palette-classic"}}, "overrides": []},
            "options": {"reduceOptions": {"values": True, "calcs": ["lastNotNull"], "fields": ""},
                        "pieType": "donut", "displayLabels": [],
                        "legend": {"showLegend": True, "displayMode": "table", "placement": "right", "values": ["value", "percent"]},
                        "tooltip": {"mode": "single", "sort": "none"}},
        })

    def bargauge(self, title, target, unit="none", w=12, h=8, color=GREEN, description=""):
        return self._add({
            "type": "bargauge", "title": title, "description": description, "gridPos": self.place(w, h),
            "datasource": target["datasource"], "targets": [target],
            "fieldConfig": {"defaults": {"unit": unit, "decimals": 0, "min": 0, "color": {"mode": "fixed", "fixedColor": color}},
                            "overrides": []},
            "options": {"reduceOptions": {"values": True, "calcs": ["lastNotNull"], "fields": ""},
                        "orientation": "horizontal", "displayMode": "basic", "showUnfilled": True,
                        "valueMode": "color", "namePlacement": "left", "sizing": "auto", "minVizHeight": 16, "maxVizHeight": 24},
        })

    def table(self, title, target, w=12, h=9, overrides=None, description=""):
        return self._add({
            "type": "table", "title": title, "description": description, "gridPos": self.place(w, h),
            "datasource": target["datasource"], "targets": [target],
            "fieldConfig": {"defaults": {"custom": {"align": "auto", "cellOptions": {"type": "auto"}, "filterable": True}},
                            "overrides": overrides or []},
            "options": {"showHeader": True, "cellHeight": "sm", "footer": {"show": False, "reducer": ["sum"], "fields": ""}},
        })

    def text(self, content, w=24, h=3):
        return self._add({"type": "text", "title": "", "gridPos": self.place(w, h), "transparent": True,
                          "options": {"mode": "markdown", "content": content}})

    def sql_variable(self, name, label, query):
        self.variables.append({
            "type": "query", "name": name, "label": label, "datasource": PG, "query": query, "definition": query,
            "refresh": 1, "multi": True, "includeAll": True, "current": {"selected": True, "text": ["All"], "value": ["$__all"]},
            "sort": 1, "hide": 0, "options": [],
        })

    def json(self):
        return {
            "uid": self.uid, "title": self.title, "description": self.description, "tags": self.tags,
            "timezone": "browser", "editable": True, "graphTooltip": 1, "schemaVersion": 39, "version": 1,
            "refresh": self.refresh, "time": {"from": self.time_from, "to": "now"},
            "timepicker": {}, "fiscalYearStartMonth": 0, "liveNow": False,
            "templating": {"list": self.variables}, "annotations": {"list": []},
            "links": [{"title": "Other PharmaTrack dashboards", "type": "dashboards", "tags": ["pharmatrack"],
                       "asDropdown": True, "includeVars": False, "keepTime": True}],
            "panels": self.panels,
        }


def colour_by(name, steps, mode="color-background"):
    return {"matcher": {"id": "byName", "options": name}, "properties": [
        {"id": "custom.cellOptions", "value": {"type": mode, "mode": "basic"}},
        {"id": "thresholds", "value": {"mode": "absolute", "steps": steps}},
        {"id": "color", "value": {"mode": "thresholds"}},
    ]}


def unit_override(name, unit, decimals=0):
    return {"matcher": {"id": "byName", "options": name},
            "properties": [{"id": "unit", "value": unit}, {"id": "decimals", "value": decimals}]}


# ================================================================== inventory
def inventory():
    b = Board("pharmatrack-inventory", "PharmaTrack · Inventory & Expiry",
              "Stock value, low stock, expiry timeline and losses. Reads PostgreSQL views.", ["pharmatrack", "inventory"],
              time_from="now-6M", refresh="5m")
    s = b.sql
    b.stat("Sellable stock (at cost)", s("SELECT COALESCE(SUM(stock_value),0) AS value FROM v_medicine_stock WHERE is_active"),
           unit="currencyINR", description="Units in non-expired batches × purchase cost.")
    b.stat("Active medicines", s("SELECT COUNT(*) AS value FROM inventory_medicine WHERE is_active"))
    b.stat("Below reorder level", s("SELECT COUNT(*) AS value FROM v_medicine_stock WHERE is_active AND is_low_stock"),
           steps=[{"color": GREEN, "value": None}, {"color": AMBER, "value": 1}])
    b.stat("Out of stock", s("SELECT COUNT(*) AS value FROM v_medicine_stock WHERE is_active AND stock = 0"),
           steps=[{"color": GREEN, "value": None}, {"color": RED, "value": 1}])
    b.stat("Batches expiring ≤ 30 days",
           s("SELECT COUNT(*) AS value FROM v_batch_expiry WHERE status = 'CRITICAL' AND quantity_available > 0"),
           steps=[{"color": GREEN, "value": None}, {"color": RED, "value": 1}])
    b.stat("Expired stock still on shelf",
           s("SELECT COALESCE(SUM(stock_value),0) AS value FROM v_batch_expiry WHERE status = 'EXPIRED' AND quantity_available > 0"),
           unit="currencyINR", steps=[{"color": GREEN, "value": None}, {"color": RED, "value": 1}],
           description="Remove and write these off; they can't be sold.")

    b.section("Expiry")
    b.barchart("Stock value expiring per week (next 13 weeks)", s("""
SELECT to_char(w.week, 'DD Mon') AS "Week of",
       COALESCE(SUM(e.stock_value), 0) AS "Value at cost"
FROM generate_series(date_trunc('week', pharma_today()), date_trunc('week', pharma_today()) + interval '12 weeks', interval '1 week') AS w(week)
LEFT JOIN v_batch_expiry e
       ON date_trunc('week', e.expiry_date) = w.week AND e.quantity_available > 0 AND e.expiry_date >= pharma_today()
GROUP BY w.week
ORDER BY w.week
"""), x_field="Week of", unit="currencyINR", w=16, h=9, color=AMBER,
               description="How much money is about to expire. Sell, discount or return these first.")
    b.pie("Expiry status of stock (by value)", s("""
SELECT CASE status WHEN 'EXPIRED' THEN 'Expired' WHEN 'CRITICAL' THEN 'Under 30 days'
                   WHEN 'WARNING' THEN '30–90 days' ELSE 'Over 90 days' END AS status,
       SUM(stock_value) AS value
FROM v_batch_expiry WHERE quantity_available > 0
GROUP BY status ORDER BY MIN(days_to_expiry)
"""), unit="currencyINR", w=8, h=9)
    b.table("Batches expiring within 90 days", s("""
SELECT medicine AS "Medicine", batch_number AS "Batch", supplier AS "Supplier",
       quantity_available AS "Units", stock_value AS "Value", expiry_date AS "Expiry", days_to_expiry AS "Days left"
FROM v_batch_expiry
WHERE quantity_available > 0 AND days_to_expiry <= 90
ORDER BY days_to_expiry
"""), w=24, h=10, overrides=[
        colour_by("Days left", [{"color": RED, "value": None}, {"color": AMBER, "value": 31}, {"color": GREEN, "value": 91}]),
        unit_override("Value", "currencyINR", 2),
    ])

    b.section("Stock levels")
    b.table("Reorder now (below reorder level)", s("""
SELECT display_name AS "Medicine", category AS "Category", stock AS "In stock",
       reorder_level AS "Reorder level", reorder_level - stock AS "Short by"
FROM v_medicine_stock
WHERE is_active AND is_low_stock
ORDER BY stock, display_name
"""), w=12, h=9, overrides=[colour_by("In stock", [{"color": RED, "value": None}, {"color": AMBER, "value": 1}])])
    b.pie("Stock value by category", s("""
SELECT category, SUM(stock_value) AS value FROM v_medicine_stock GROUP BY category ORDER BY value DESC
"""), unit="currencyINR", w=12, h=9)
    b.bargauge("Stock value by supplier", s("""
SELECT supplier, SUM(stock_value) AS value FROM v_batch_expiry
WHERE quantity_available > 0 AND status <> 'EXPIRED' GROUP BY supplier ORDER BY value DESC
"""), unit="currencyINR", w=12, h=8)
    b.timeseries("Units received vs sold per week", [
        s(f"""
SELECT date_trunc('week', received_date)::timestamptz AS time, SUM(quantity_received) AS "Received"
FROM inventory_batch WHERE $__timeFilter(received_date::timestamptz) GROUP BY 1 ORDER BY 1
""", fmt="time_series"),
        s(f"""
SELECT date_trunc('week', sold_at AT TIME ZONE 'Asia/Kolkata') AT TIME ZONE 'Asia/Kolkata' AS time, SUM(quantity) AS "Sold"
FROM v_sales_detail WHERE $__timeFilter(sold_at) GROUP BY 1 ORDER BY 1
""", fmt="time_series", ref="B"),
    ], w=12, h=8, bars=True, colors={"Received": BLUE, "Sold": GREEN})

    b.section("Losses")
    b.stat("Loss from expiry in range", s("""
SELECT COALESCE(SUM(loss_value),0) AS value FROM v_stock_loss WHERE $__timeFilter(happened_at)
"""), unit="currencyINR", w=6, h=8, steps=[{"color": GREEN, "value": None}, {"color": RED, "value": 1}],
           description="Expired units on the shelf plus written-off units, at purchase cost.")
    b.timeseries("Loss from expired stock per month", [s("""
SELECT date_trunc('month', happened_at) AS time,
       SUM(loss_value) FILTER (WHERE kind = 'WRITTEN_OFF') AS "Written off",
       SUM(loss_value) FILTER (WHERE kind = 'ON_SHELF_EXPIRED') AS "Expired, still on shelf"
FROM v_stock_loss WHERE $__timeFilter(happened_at) GROUP BY 1 ORDER BY 1
""", fmt="time_series")], unit="currencyINR", w=9, h=8, bars=True, stack=True,
                 colors={"Written off": GREY, "Expired, still on shelf": RED})
    b.table("Biggest expiry losses", s("""
SELECT medicine AS "Medicine", category AS "Category", SUM(quantity) AS "Units", SUM(loss_value) AS "Loss"
FROM v_stock_loss WHERE $__timeFilter(happened_at) GROUP BY 1, 2 ORDER BY "Loss" DESC LIMIT 10
"""), w=9, h=8, overrides=[unit_override("Loss", "currencyINR", 2)])
    return b


# ================================================================== sales
def sales():
    b = Board("pharmatrack-sales", "PharmaTrack · Sales", "Revenue, bills, best sellers and profit from PostgreSQL.",
              ["pharmatrack", "sales"])
    b.sql_variable("category", "Category", "SELECT name FROM inventory_category ORDER BY name")
    s = b.sql
    in_cat = "category IN ($category)"
    b.stat("Revenue", s(f"""
SELECT COALESCE(SUM(line_total),0) AS value FROM v_sales_detail WHERE $__timeFilter(sold_at) AND {in_cat}
"""), unit="currencyINR", description="Before bill-level discounts.")
    b.stat("Gross profit", s(f"""
SELECT COALESCE(SUM(gross_profit),0) AS value FROM v_sales_detail WHERE $__timeFilter(sold_at) AND {in_cat}
"""), unit="currencyINR", steps=[{"color": GREEN, "value": None}], description="Selling price minus batch purchase cost.")
    b.stat("Bills", s(f"""
SELECT COUNT(DISTINCT sale_id) AS value FROM v_sales_detail WHERE $__timeFilter(sold_at) AND {in_cat}
"""))
    b.stat("Average bill", s("""
SELECT COALESCE(AVG(total_amount),0) AS value FROM inventory_sale WHERE $__timeFilter(created_at)
"""), unit="currencyINR")
    b.stat("Units sold", s(f"""
SELECT COALESCE(SUM(quantity),0) AS value FROM v_sales_detail WHERE $__timeFilter(sold_at) AND {in_cat}
"""))
    b.stat("Revenue today", s("""
SELECT COALESCE(SUM(total_amount),0) AS value FROM inventory_sale
WHERE (created_at AT TIME ZONE 'Asia/Kolkata')::date = pharma_today()
"""), unit="currencyINR", steps=[{"color": GREEN, "value": None}])

    b.timeseries("Daily revenue", [s(f"""
SELECT {IST_DAY.format(col='sold_at')} AS time, SUM(line_total) AS "Revenue", SUM(gross_profit) AS "Gross profit"
FROM v_sales_detail WHERE $__timeFilter(sold_at) AND {in_cat}
GROUP BY 1 ORDER BY 1
""", fmt="time_series")], unit="currencyINR", w=16, h=9, bars=True, colors={"Revenue": DEEP, "Gross profit": "#7fc4a4"})
    b.pie("Revenue by category", s(f"""
SELECT category, SUM(line_total) AS value FROM v_sales_detail
WHERE $__timeFilter(sold_at) AND {in_cat} GROUP BY category ORDER BY value DESC
"""), unit="currencyINR", w=8, h=9)

    b.bargauge("Top 10 medicines by units sold", s(f"""
SELECT medicine, SUM(quantity) AS units FROM v_sales_detail
WHERE $__timeFilter(sold_at) AND {in_cat} GROUP BY medicine ORDER BY units DESC LIMIT 10
"""), w=12, h=10)
    b.bargauge("Top 10 medicines by gross profit", s(f"""
SELECT medicine, SUM(gross_profit) AS profit FROM v_sales_detail
WHERE $__timeFilter(sold_at) AND {in_cat} GROUP BY medicine ORDER BY profit DESC LIMIT 10
"""), unit="currencyINR", w=12, h=10, color=BLUE)

    b.timeseries("Bills per day", [s("""
SELECT (date_trunc('day', created_at AT TIME ZONE 'Asia/Kolkata') AT TIME ZONE 'Asia/Kolkata') AS time, COUNT(*) AS "Bills"
FROM inventory_sale WHERE $__timeFilter(created_at) GROUP BY 1 ORDER BY 1
""", fmt="time_series")], w=12, h=8, colors={"Bills": GREEN})
    b.barchart("Busiest hours of the day", s("""
SELECT lpad(h::text, 2, '0') || ':00' AS "Hour", COUNT(s.id) AS "Bills"
FROM generate_series(8, 22) AS h
LEFT JOIN inventory_sale s
       ON extract(hour FROM s.created_at AT TIME ZONE 'Asia/Kolkata') = h AND $__timeFilter(s.created_at)
GROUP BY h ORDER BY h
"""), x_field="Hour", w=6, h=8, description="Plan counter staff around the peaks.")
    b.pie("Payment methods", s("""
SELECT payment_method AS method, SUM(total_amount) AS value FROM inventory_sale
WHERE $__timeFilter(created_at) GROUP BY 1 ORDER BY 2 DESC
"""), unit="currencyINR", w=6, h=8)

    b.table("Latest bills", s("""
SELECT s.created_at AS "Time", s.invoice_number AS "Bill", NULLIF(s.customer_name, '') AS "Customer",
       s.payment_method AS "Payment", COUNT(i.id) AS "Lines", s.total_amount AS "Total"
FROM inventory_sale s LEFT JOIN inventory_saleitem i ON i.sale_id = s.id
WHERE $__timeFilter(s.created_at)
GROUP BY s.id ORDER BY s.created_at DESC LIMIT 50
"""), w=24, h=9, overrides=[unit_override("Total", "currencyINR", 2),
                             {"matcher": {"id": "byName", "options": "Time"},
                              "properties": [{"id": "unit", "value": "dateTimeAsLocal"}]}])
    return b


# ================================================================== system
def system():
    b = Board("pharmatrack-system", "PharmaTrack · System & API",
              "Django API traffic, latency and errors, PostgreSQL health and container resources (Prometheus).",
              ["pharmatrack", "system"], time_from="now-1h", refresh="30s")
    p = b.prom
    b.stat("API status", p('min(up{job="django"})', instant=True), w=4,
           steps=[{"color": RED, "value": None}, {"color": GREEN, "value": 1}], color_mode="background")
    b.stat("Requests / second", p("sum(rate(django_http_requests_total_by_method_total[$__rate_interval]))"),
           unit="reqps", decimals=2)
    b.stat("p95 response time", p(
        "histogram_quantile(0.95, sum by (le) (rate(django_http_requests_latency_seconds_by_view_method_bucket[$__rate_interval])))"),
        unit="s", decimals=3, steps=[{"color": GREEN, "value": None}, {"color": AMBER, "value": 0.3}, {"color": RED, "value": 1}])
    b.stat("Server errors (5xx) / min", p(
        'sum(rate(django_http_responses_total_by_status_total{status=~"5.."}[$__rate_interval])) * 60 or vector(0)'),
        decimals=2, steps=[{"color": GREEN, "value": None}, {"color": RED, "value": 0.01}])
    b.stat("Database connections", p('sum(pg_stat_database_numbackends{datname="pharmatrack"})'),
           steps=[{"color": GREEN, "value": None}, {"color": AMBER, "value": 80}])
    b.stat("Database size", p('pg_database_size_bytes{datname="pharmatrack"}'), unit="bytes", decimals=1)

    b.section("API")
    b.timeseries("Requests per second by status", [p(
        "sum by (status) (rate(django_http_responses_total_by_status_total[$__rate_interval]))", "{{status}}")],
        unit="reqps", w=12, h=8, stack=True)
    b.timeseries("Response time", [
        p("histogram_quantile(0.50, sum by (le) (rate(django_http_requests_latency_seconds_by_view_method_bucket[$__rate_interval])))", "p50"),
        p("histogram_quantile(0.95, sum by (le) (rate(django_http_requests_latency_seconds_by_view_method_bucket[$__rate_interval])))", "p95", ref="B"),
        p("histogram_quantile(0.99, sum by (le) (rate(django_http_requests_latency_seconds_by_view_method_bucket[$__rate_interval])))", "p99", ref="C"),
    ], unit="s", w=12, h=8, colors={"p50": GREEN, "p95": AMBER, "p99": RED})
    b.timeseries("Slowest endpoints (p95)", [p(
        'topk(5, histogram_quantile(0.95, sum by (le, view) (rate(django_http_requests_latency_seconds_by_view_method_bucket{view!="prometheus-django-metrics"}[$__rate_interval]))))',
        "{{view}}")], unit="s", w=12, h=8)
    b.timeseries("Database queries per second", [
        p("sum(rate(django_db_execute_total[$__rate_interval]))", "queries"),
        p("sum(rate(django_db_errors_total[$__rate_interval])) or vector(0)", "errors", ref="B"),
    ], unit="ops", w=12, h=8, colors={"queries": BLUE, "errors": RED})

    b.section("Business events")
    b.timeseries("Bills created per minute", [p(
        "sum by (payment_method) (rate(pharmatrack_sales_created_total[$__rate_interval])) * 60", "{{payment_method}}")],
        w=12, h=8, bars=True, stack=True, decimals=1)
    b.timeseries("Login attempts per minute", [p(
        "sum by (result) (rate(pharmatrack_login_attempts_total[$__rate_interval])) * 60", "{{result}}")],
        w=12, h=8, colors={"success": GREEN, "failure": RED}, decimals=1)

    b.section("Containers")
    b.timeseries("CPU by container", [p(
        'sum by (name) (rate(container_cpu_usage_seconds_total{name=~".+"}[$__rate_interval])) * 100', "{{name}}")],
        unit="percent", w=12, h=8)
    b.timeseries("Memory by container", [p('sum by (name) (container_memory_working_set_bytes{name=~".+"})', "{{name}}")],
                 unit="bytes", w=12, h=8)
    b.timeseries("Network received by container", [p(
        'sum by (name) (rate(container_network_receive_bytes_total{name=~".+"}[$__rate_interval]))', "{{name}}")],
        unit="Bps", w=12, h=8)
    b.timeseries("PostgreSQL transactions per second", [
        p('sum(rate(pg_stat_database_xact_commit{datname="pharmatrack"}[$__rate_interval]))', "commits"),
        p('sum(rate(pg_stat_database_xact_rollback{datname="pharmatrack"}[$__rate_interval]))', "rollbacks", ref="B"),
    ], unit="ops", w=12, h=8, colors={"commits": GREEN, "rollbacks": RED})
    return b


BOARDS = [inventory, sales, system]

if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    for make in BOARDS:
        board = make()
        path = OUT / f"{board.uid}.json"
        path.write_text(json.dumps(board.json(), indent=2, ensure_ascii=False) + "\n")
        print(f"wrote {path.relative_to(OUT.parent.parent)} ({len(board.panels)} panels)")
