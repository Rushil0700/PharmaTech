"""
Generate live bills so Grafana graphs move during a demo.

    python manage.py simulate_sales                 # one bill every ~10 s, forever
    python manage.py simulate_sales --interval 3 --count 50
"""
import random
import time

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from prometheus_client import start_http_server

from inventory.models import Medicine
from inventory.services import StockError, create_sale


class Command(BaseCommand):
    help = "Continuously create random sales (demo traffic for Grafana)."

    def add_arguments(self, parser):
        parser.add_argument("--interval", type=float, default=10.0, help="Average seconds between bills")
        parser.add_argument("--count", type=int, default=0, help="Stop after N bills (0 = run forever)")
        parser.add_argument("--metrics-port", type=int, default=0,
                            help="Expose this process's pharmatrack_* counters for Prometheus (0 = off)")

    def handle(self, *args, interval, count, metrics_port, **options):
        # Bills made here increment counters in this process, not in the backend's /metrics.
        if metrics_port:
            start_http_server(metrics_port)
        user = User.objects.filter(username="pharmacist").first() or User.objects.filter(is_superuser=True).first()
        made = 0
        self.stdout.write(f"Simulating sales every ~{interval}s. Ctrl+C to stop.")
        while not count or made < count:
            meds = list(Medicine.objects.filter(is_active=True))
            if not meds:
                self.stderr.write("No medicines found. Run seed_data first.")
                return
            picks = random.sample(meds, k=min(len(meds), random.choice([1, 1, 2, 3])))
            try:
                sale = create_sale(
                    items=[{"medicine": m, "quantity": random.choice([1, 1, 2, 3])} for m in picks],
                    user=user,
                    doctor_name="Dr. Demo" if any(m.requires_prescription for m in picks) else "",
                    payment_method=random.choice(["UPI", "UPI", "CASH", "CARD"]),
                )
                made += 1
                self.stdout.write(f"  {sale.invoice_number}  ₹{sale.total_amount}")
            except StockError as exc:
                self.stdout.write(f"  skipped: {exc}")
            time.sleep(max(0.5, random.uniform(interval * 0.5, interval * 1.5)))
