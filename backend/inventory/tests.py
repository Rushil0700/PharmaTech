from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.db import IntegrityError, connection, transaction
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import Batch, Category, Medicine, PurchaseOrder, PurchaseOrderItem, Sale, SaleItem, Supplier
from .permissions import PHARMACIST, STORE_STAFF
from .services import StockError, create_sale


class BaseData(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.cat = Category.objects.create(name="Analgesics")
        self.sup = Supplier.objects.create(name="MedLine")
        self.med = Medicine.objects.create(name="Paracetamol", strength="500 mg", category=self.cat,
                                           unit_price=Decimal("10.00"), reorder_level=20)
        self.rx = Medicine.objects.create(name="Azithromycin", strength="500 mg", category=self.cat,
                                          unit_price=Decimal("100.00"), requires_prescription=True)

    def batch(self, med=None, qty=10, days=100, number=None, received_days_ago=10):
        med = med or self.med
        return Batch.objects.create(
            medicine=med, supplier=self.sup, batch_number=number or f"B{Batch.objects.count() + 1}",
            quantity_received=qty, quantity_available=qty, cost_price=Decimal("6.00"),
            mfg_date=self.today - timedelta(days=400), expiry_date=self.today + timedelta(days=days),
            received_date=self.today - timedelta(days=received_days_ago),
        )

    def user(self, username, role=None, admin=False):
        u = User.objects.create_user(username, password="pass1234", is_staff=admin)
        if role:
            u.groups.add(Group.objects.get_or_create(name=role)[0])
        return u


class FefoBillingTests(BaseData):
    def test_sells_earliest_expiry_first_and_splits_batches(self):
        late = self.batch(qty=10, days=300, number="LATE")
        early = self.batch(qty=4, days=40, number="EARLY")
        sale = create_sale(items=[{"medicine": self.med, "quantity": 6}])

        early.refresh_from_db()
        late.refresh_from_db()
        self.assertEqual(early.quantity_available, 0)
        self.assertEqual(late.quantity_available, 8)
        self.assertEqual(sale.items.count(), 2)
        self.assertEqual(sale.total_amount, Decimal("60.00"))
        self.assertTrue(sale.invoice_number.startswith("INV-"))

    def test_expired_batches_are_never_sold(self):
        self.batch(qty=50, days=-1, number="EXP")
        with self.assertRaises(StockError):
            create_sale(items=[{"medicine": self.med, "quantity": 1}])
        self.assertEqual(Sale.objects.count(), 0)  # whole bill rolled back

    def test_insufficient_stock_rolls_back_entire_bill(self):
        b = self.batch(qty=3)
        with self.assertRaises(StockError):
            create_sale(items=[{"medicine": self.med, "quantity": 5}])
        b.refresh_from_db()
        self.assertEqual(b.quantity_available, 3)

    def test_prescription_medicine_needs_doctor(self):
        self.batch(med=self.rx, qty=5)
        with self.assertRaises(StockError):
            create_sale(items=[{"medicine": self.rx, "quantity": 1}])
        create_sale(items=[{"medicine": self.rx, "quantity": 1}], doctor_name="Dr. Rao")

    def test_discount(self):
        self.batch(qty=10)
        sale = create_sale(items=[{"medicine": self.med, "quantity": 10}], discount=Decimal("5"))
        self.assertEqual(sale.total_amount, Decimal("95.00"))
        with self.assertRaises(StockError):
            create_sale(items=[{"medicine": self.med, "quantity": 0}])


class TriggerTests(BaseData):
    """The stock rules live in PostgreSQL, so they hold even for raw SQL writes."""

    def test_trigger_decrements_and_cancel_restores(self):
        b = self.batch(qty=10)
        sale = create_sale(items=[{"medicine": self.med, "quantity": 4}])
        b.refresh_from_db()
        self.assertEqual(b.quantity_available, 6)
        sale.delete()
        b.refresh_from_db()
        self.assertEqual(b.quantity_available, 10)

    def test_trigger_blocks_overselling_at_db_level(self):
        b = self.batch(qty=2)
        sale = Sale.objects.create()
        with self.assertRaises(IntegrityError), transaction.atomic():
            SaleItem.objects.create(sale=sale, batch=b, medicine=self.med, quantity=5,
                                    unit_price=Decimal("10"), line_total=Decimal("50"))

    def test_trigger_blocks_expired_batch_at_db_level(self):
        b = self.batch(qty=5, days=-3)
        sale = Sale.objects.create()
        with self.assertRaises(IntegrityError), transaction.atomic():
            SaleItem.objects.create(sale=sale, batch=b, medicine=self.med, quantity=1,
                                    unit_price=Decimal("10"), line_total=Decimal("10"))

    def test_sale_items_are_immutable(self):
        self.batch(qty=5)
        sale = create_sale(items=[{"medicine": self.med, "quantity": 1}])
        with self.assertRaises(Exception), transaction.atomic():
            SaleItem.objects.filter(sale=sale).update(quantity=3)

    def test_views_report_status(self):
        self.batch(qty=5, days=-2, number="E1")
        self.batch(qty=5, days=10, number="C1")
        self.batch(qty=5, days=60, number="W1")
        with connection.cursor() as cur:
            cur.execute("SELECT batch_number, status FROM v_batch_expiry ORDER BY batch_number")
            self.assertEqual(dict(cur.fetchall()), {"C1": "CRITICAL", "E1": "EXPIRED", "W1": "WARNING"})
            cur.execute("SELECT stock, is_low_stock FROM v_medicine_stock WHERE medicine_id = %s", [self.med.id])
            self.assertEqual(cur.fetchone(), (10, True))  # expired units excluded; 10 < reorder 20


class ApiTests(BaseData):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.pharmacist = self.user("ph", PHARMACIST)
        self.staff = self.user("st", STORE_STAFF)
        self.admin = self.user("ad", admin=True)

    def login(self, username):
        r = self.client.post("/api/auth/login/", {"username": username, "password": "pass1234"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['access']}")

    def test_requires_login(self):
        self.assertEqual(self.client.get("/api/medicines/").status_code, 401)
        self.assertEqual(self.client.get("/api/health/").status_code, 200)

    def test_me_returns_role(self):
        self.login("st")
        self.assertEqual(self.client.get("/api/auth/me/").data["role"], STORE_STAFF)

    def test_pharmacist_can_bill_staff_cannot(self):
        self.batch(qty=20)
        payload = {"items": [{"medicine": self.med.id, "quantity": 2}], "payment_method": "UPI"}
        self.login("st")
        self.assertEqual(self.client.post("/api/sales/", payload, format="json").status_code, 403)
        self.login("ph")
        r = self.client.post("/api/sales/", payload, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["total_amount"], "20.00")
        self.assertEqual(len(r.data["items"]), 1)

    def test_out_of_stock_returns_400(self):
        self.login("ph")
        r = self.client.post("/api/sales/", {"items": [{"medicine": self.med.id, "quantity": 2}]}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("in stock", r.data["detail"])

    def test_staff_manages_stock_pharmacist_cannot(self):
        data = {"medicine": self.med.id, "supplier": self.sup.id, "batch_number": "NEW1",
                "quantity_received": 30, "cost_price": "5.00",
                "mfg_date": str(self.today - timedelta(days=30)), "expiry_date": str(self.today + timedelta(days=500))}
        self.login("ph")
        self.assertEqual(self.client.post("/api/batches/", data, format="json").status_code, 403)
        self.login("st")
        r = self.client.post("/api/batches/", data, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["quantity_available"], 30)

    def test_batch_validation(self):
        self.login("st")
        r = self.client.post("/api/batches/", {
            "medicine": self.med.id, "supplier": self.sup.id, "batch_number": "BAD", "quantity_received": 5,
            "cost_price": "5", "mfg_date": str(self.today), "expiry_date": str(self.today - timedelta(days=1)),
        }, format="json")
        self.assertEqual(r.status_code, 400)

    def test_medicine_list_annotates_stock(self):
        self.batch(qty=7)
        self.batch(qty=100, days=-5)  # expired: not counted
        self.login("ph")
        r = self.client.get("/api/medicines/?search=Paracetamol")
        row = r.data["results"][0]
        self.assertEqual(row["stock"], 7)
        self.assertTrue(row["is_low_stock"])
        r = self.client.get("/api/medicines/?low_stock=1")
        self.assertEqual({m["name"] for m in r.data["results"]}, {"Paracetamol", "Azithromycin"})

    def test_purchase_order_receive_creates_batches(self):
        self.login("st")
        r = self.client.post("/api/purchase-orders/", {
            "supplier": self.sup.id, "items": [{"medicine": self.med.id, "quantity": 50, "unit_cost": "6.50"}],
        }, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        po_id, item_id = r.data["id"], r.data["items"][0]["id"]
        self.assertEqual(r.data["total_cost"], "325.00")
        r = self.client.post(f"/api/purchase-orders/{po_id}/receive/", {"batches": [{
            "item": item_id, "batch_number": "PO-B1",
            "mfg_date": str(self.today - timedelta(days=20)), "expiry_date": str(self.today + timedelta(days=700)),
        }]}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["status"], "RECEIVED")
        self.assertEqual(Batch.objects.get(batch_number="PO-B1").quantity_available, 50)
        # Receiving twice is rejected.
        r = self.client.post(f"/api/purchase-orders/{po_id}/receive/", {"batches": [{
            "item": item_id, "batch_number": "PO-B2", "mfg_date": "2026-01-01", "expiry_date": "2028-01-01"}]},
            format="json")
        self.assertEqual(r.status_code, 400)

    def test_cancel_bill_restores_stock(self):
        b = self.batch(qty=10)
        self.login("ph")
        sale_id = self.client.post("/api/sales/", {"items": [{"medicine": self.med.id, "quantity": 3}]},
                                   format="json").data["id"]
        self.assertEqual(self.client.delete(f"/api/sales/{sale_id}/").status_code, 204)
        b.refresh_from_db()
        self.assertEqual(b.quantity_available, 10)

    def test_alerts_and_dashboard(self):
        self.batch(qty=5, days=-2, number="E1")
        self.batch(qty=50, days=15, number="C1")
        self.login("st")
        r = self.client.get("/api/alerts/")
        self.assertEqual(r.data["counts"]["expired"], 1)
        self.assertEqual(r.data["counts"]["expiring_30"], 1)
        self.assertIn("Azithromycin 500 mg", [m["name"] for m in r.data["low_stock"]])
        r = self.client.get("/api/dashboard/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["expiring_30"], 1)
        self.assertEqual(r.data["stock_value"], "300.00")
        self.assertEqual(r.data["expired_value"], "30.00")
        self.assertEqual(len(r.data["sales_trend"]), 14)

    def test_only_admin_manages_users(self):
        self.login("ph")
        self.assertEqual(self.client.get("/api/users/").status_code, 403)
        self.login("ad")
        r = self.client.post("/api/users/", {"username": "new", "password": "secret12", "role": PHARMACIST},
                             format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["role"], PHARMACIST)

    def test_metrics_endpoint(self):
        self.batch(qty=5)
        create_sale(items=[{"medicine": self.med, "quantity": 1}])
        body = self.client.get("/metrics").content.decode()
        self.assertIn("pharmatrack_sales_created_total", body)
        self.assertIn("django_http_requests_total_by_method_total", body)

    def test_write_off_records_loss(self):
        b = self.batch(qty=8, days=-4)
        self.login("st")
        r = self.client.post(f"/api/batches/{b.id}/write_off/", {"quantity": 8}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["quantity_available"], 0)
        self.assertEqual(self.client.get("/api/dashboard/").data["written_off_30d"], "48.00")
        with connection.cursor() as cur:
            cur.execute("SELECT kind, loss_value FROM v_stock_loss")
            self.assertEqual(cur.fetchall(), [("WRITTEN_OFF", Decimal("48.00"))])
        self.assertEqual(self.client.post(f"/api/batches/{b.id}/write_off/", {"quantity": 1}, format="json").status_code, 400)
