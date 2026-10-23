"""
Custom Prometheus metrics exposed at /metrics alongside django-prometheus'
built-in HTTP/DB metrics. Grafana's "System & API" dashboard plots these.
"""
from prometheus_client import Counter, Histogram

SALES_TOTAL = Counter(
    "pharmatrack_sales_created_total", "Bills created", ["payment_method"]
)
UNITS_SOLD = Counter("pharmatrack_units_sold_total", "Medicine units sold")
SALE_AMOUNT = Histogram(
    "pharmatrack_sale_amount_rupees",
    "Bill value in rupees",
    buckets=(50, 100, 250, 500, 1000, 2500, 5000, 10000),
)
LOGIN_ATTEMPTS = Counter("pharmatrack_login_attempts_total", "Login attempts", ["result"])


def record_sale(amount, units, payment_method):
    SALES_TOTAL.labels(payment_method=payment_method).inc()
    UNITS_SOLD.inc(units)
    SALE_AMOUNT.observe(float(amount))
