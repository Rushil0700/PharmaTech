"""
Load realistic demo data so the app and every Grafana panel have something to show.

    python manage.py seed_data            # only if the database is empty
    python manage.py seed_data --reset    # wipe inventory data and reload
    python manage.py seed_data --days 120 # amount of sales history

Creates demo users (admin / pharmacist / staff), suppliers, ~40 common medicines,
batches with a deliberate mix of healthy, near-expiry and expired stock, a few
deliberately low-stock items, purchase orders and N days of sales history.
"""
import random
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from inventory.models import (
    Batch, Category, Medicine, PurchaseOrder, PurchaseOrderItem, Sale, StockWriteOff, Supplier,
)
from inventory.permissions import PHARMACIST, STORE_STAFF
from inventory.services import StockError, create_sale

CATEGORIES = {
    "Analgesics & Antipyretics": "Pain relief and fever",
    "Antibiotics": "Bacterial infections",
    "Antidiabetics": "Blood sugar control",
    "Cardiovascular": "Blood pressure, cholesterol, heart",
    "Gastrointestinal": "Acidity, digestion, ORS",
    "Allergy & Cold": "Antihistamines and cough/cold",
    "Respiratory": "Asthma and inhalers",
    "Vitamins & Supplements": "Nutritional supplements",
    "Dermatology": "Creams and ointments",
    "First Aid": "Antiseptics and dressings",
}

# name, strength, brand, category, form, price, reorder, rx, popularity
MEDICINES = [
    ("Paracetamol", "650 mg", "Dolo", "Analgesics & Antipyretics", "TABLET", "32.00", 60, False, 10),
    ("Paracetamol", "500 mg", "Crocin", "Analgesics & Antipyretics", "TABLET", "24.50", 50, False, 8),
    ("Ibuprofen", "400 mg", "Brufen", "Analgesics & Antipyretics", "TABLET", "28.00", 30, False, 5),
    ("Diclofenac", "50 mg", "Voveran", "Analgesics & Antipyretics", "TABLET", "45.00", 25, True, 3),
    ("Aceclofenac + Paracetamol", "100/325 mg", "Zerodol-P", "Analgesics & Antipyretics", "TABLET", "68.00", 25, True, 4),
    ("Azithromycin", "500 mg", "Azithral", "Antibiotics", "TABLET", "119.00", 20, True, 4),
    ("Amoxicillin + Clavulanate", "625 mg", "Augmentin", "Antibiotics", "TABLET", "223.00", 20, True, 3),
    ("Cefixime", "200 mg", "Taxim-O", "Antibiotics", "TABLET", "109.00", 15, True, 2),
    ("Ciprofloxacin", "500 mg", "Ciplox", "Antibiotics", "TABLET", "38.00", 15, True, 2),
    ("Doxycycline", "100 mg", "Doxt-SL", "Antibiotics", "CAPSULE", "96.00", 15, True, 1),
    ("Metformin", "500 mg", "Glycomet", "Antidiabetics", "TABLET", "34.00", 40, True, 6),
    ("Glimepiride", "2 mg", "Amaryl", "Antidiabetics", "TABLET", "155.00", 20, True, 3),
    ("Sitagliptin", "100 mg", "Januvia", "Antidiabetics", "TABLET", "398.00", 10, True, 1),
    ("Amlodipine", "5 mg", "Amlong", "Cardiovascular", "TABLET", "42.00", 40, True, 5),
    ("Telmisartan", "40 mg", "Telma", "Cardiovascular", "TABLET", "118.00", 30, True, 5),
    ("Atorvastatin", "10 mg", "Atorva", "Cardiovascular", "TABLET", "96.00", 30, True, 4),
    ("Aspirin", "75 mg", "Ecosprin", "Cardiovascular", "TABLET", "6.50", 40, False, 4),
    ("Metoprolol", "25 mg", "Metolar", "Cardiovascular", "TABLET", "58.00", 20, True, 2),
    ("Pantoprazole", "40 mg", "Pan", "Gastrointestinal", "TABLET", "155.00", 40, False, 7),
    ("Omeprazole", "20 mg", "Omez", "Gastrointestinal", "CAPSULE", "62.00", 30, False, 4),
    ("Ondansetron", "4 mg", "Emeset", "Gastrointestinal", "TABLET", "52.00", 15, True, 2),
    ("ORS Powder", "21.8 g", "Electral", "Gastrointestinal", "POWDER", "22.00", 50, False, 6),
    ("Antacid Gel", "200 ml", "Digene", "Gastrointestinal", "SYRUP", "128.00", 15, False, 3),
    ("Cetirizine", "10 mg", "Cetzine", "Allergy & Cold", "TABLET", "19.00", 40, False, 6),
    ("Levocetirizine + Montelukast", "5/10 mg", "Montair-LC", "Allergy & Cold", "TABLET", "182.00", 25, True, 4),
    ("Cough Syrup (Dextromethorphan)", "100 ml", "Benadryl DR", "Allergy & Cold", "SYRUP", "118.00", 20, False, 4),
    ("Xylometazoline Nasal Drops", "0.1%", "Otrivin", "Allergy & Cold", "DROPS", "96.00", 15, False, 3),
    ("Salbutamol Inhaler", "100 mcg", "Asthalin", "Respiratory", "INHALER", "155.00", 10, True, 2),
    ("Budesonide + Formoterol Inhaler", "200/6 mcg", "Foracort", "Respiratory", "INHALER", "395.00", 8, True, 1),
    ("Vitamin D3", "60000 IU", "Uprise-D3", "Vitamins & Supplements", "CAPSULE", "126.00", 20, False, 3),
    ("Vitamin B-Complex", "", "Becosules", "Vitamins & Supplements", "CAPSULE", "49.00", 30, False, 5),
    ("Calcium + Vitamin D3", "500 mg", "Shelcal", "Vitamins & Supplements", "TABLET", "118.00", 25, False, 4),
    ("Iron + Folic Acid", "", "Livogen", "Vitamins & Supplements", "TABLET", "68.00", 20, False, 2),
    ("Multivitamin", "", "Supradyn", "Vitamins & Supplements", "TABLET", "48.00", 25, False, 3),
    ("Clotrimazole Cream", "1% 15 g", "Candid", "Dermatology", "OINTMENT", "92.00", 15, False, 2),
    ("Mupirocin Ointment", "2% 5 g", "T-Bact", "Dermatology", "OINTMENT", "142.00", 10, True, 1),
    ("Calamine Lotion", "100 ml", "Lacto Calamine", "Dermatology", "OTHER", "125.00", 10, False, 1),
    ("Povidone-Iodine Solution", "5% 100 ml", "Betadine", "First Aid", "OTHER", "118.00", 15, False, 2),
    ("Antiseptic Liquid", "250 ml", "Dettol", "First Aid", "OTHER", "135.00", 15, False, 2),
    ("Insulin Glargine Injection", "100 IU/ml", "Basalog", "Antidiabetics", "INJECTION", "720.00", 6, True, 1),
]

# Deliberately keep these short of stock so low-stock alerts fire in the demo.
LOW_STOCK_DEMO = {"Doxycycline", "Sitagliptin", "Salbutamol Inhaler", "Mupirocin Ointment"}

SUPPLIERS = [
    ("MedLine Distributors", "Rakesh Shah", "+91 98250 11223", "orders@medline.example", "Ahmedabad, Gujarat", "24AAACM1234F1Z5"),
    ("Sanjeevani Pharma Agencies", "Priya Nair", "+91 98980 44556", "sales@sanjeevani.example", "Vadodara, Gujarat", "24AAGCS5678K1Z2"),
    ("HealthFirst Wholesale", "Imran Qureshi", "+91 99099 77889", "supply@healthfirst.example", "Surat, Gujarat", "24AAHCH9012L1Z9"),
    ("Arogya Medical Supplies", "Neha Patel", "+91 97240 33445", "contact@arogya.example", "Rajkot, Gujarat", "24AAJCA3456M1Z1"),
    ("CarePlus Pharma Traders", "Vikram Joshi", "+91 96620 99887", "info@careplus.example", "Mumbai, Maharashtra", "27AAKCC7890N1Z4"),
]

CUSTOMERS = ["Amit", "Sneha", "Rahul", "Pooja", "Karan", "Riya", "Arjun", "Meera", "Rohan", "Kavya",
             "Harsh", "Diya", "Manish", "Nisha", "Yash", "Jinal", "Dev", "Isha", "", "", "", ""]
DOCTORS = ["Dr. Mehta", "Dr. Desai", "Dr. Iyer", "Dr. Kapoor", "Dr. Trivedi", "Dr. Rao"]

DEMO_USERS = [
    ("admin", "admin123", "Admin", "Asha", "Admin"),
    ("pharmacist", "pharma123", PHARMACIST, "Ravi", "Pharmacist"),
    ("staff", "staff123", STORE_STAFF, "Sunil", "Storekeeper"),
]


class Command(BaseCommand):
    help = "Load demo data (users, suppliers, medicines, batches, purchase orders, sales history)."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete existing inventory data first")
        parser.add_argument("--days", type=int, default=90, help="Days of sales history to generate")
        parser.add_argument("--seed", type=int, default=42, help="Random seed for repeatable data")

    def handle(self, *args, days, reset, seed, **options):
        rng = random.Random(seed)
        if reset:
            self.stdout.write("Removing existing inventory data…")
            self._wipe()
        elif Medicine.objects.exists():
            self.stdout.write(self.style.WARNING("Data already present; skipping (use --reset to reload)."))
            return

        users = self._users()
        today = timezone.localdate()
        with transaction.atomic():
            categories = {n: Category.objects.create(name=n, description=d) for n, d in CATEGORIES.items()}
            suppliers = [Supplier.objects.create(name=n, contact_person=c, phone=p, email=e, address=a, gstin=g)
                         for n, c, p, e, a, g in SUPPLIERS]
            medicines = self._medicines(categories)
            self._batches_and_orders(rng, medicines, suppliers, users["staff"], today, days)
        self.stdout.write(f"Catalogue: {len(medicines)} medicines, {Batch.objects.count()} batches.")

        bills = self._sales(rng, medicines, users, today, days)
        self._write_offs(rng, users["staff"], today)
        self.stdout.write(self.style.SUCCESS(
            f"Done: {bills} bills over {days} days. Logins: admin/admin123, pharmacist/pharma123, staff/staff123"
        ))

    # ------------------------------------------------------------------ helpers

    def _wipe(self):
        with transaction.atomic():
            StockWriteOff.objects.all().delete()
            Sale.objects.all().delete()  # trigger restores stock; batches are deleted next anyway
            Batch.objects.all().delete()
            PurchaseOrder.objects.all().delete()
            Medicine.objects.all().delete()
            Supplier.objects.all().delete()
            Category.objects.all().delete()

    def _users(self):
        users = {}
        for username, password, role, first, last in DEMO_USERS:
            user, created = User.objects.get_or_create(
                username=username, defaults={"first_name": first, "last_name": last}
            )
            if created:
                user.set_password(password)
            if role == "Admin":
                user.is_staff = user.is_superuser = True
            else:
                user.groups.add(Group.objects.get_or_create(name=role)[0])
            user.save()
            users[username] = user
        Group.objects.get_or_create(name=PHARMACIST)
        Group.objects.get_or_create(name=STORE_STAFF)
        return users

    def _medicines(self, categories):
        meds = []
        for name, strength, brand, cat, form, price, reorder, rx, pop in MEDICINES:
            med = Medicine.objects.create(
                name=name, strength=strength, brand=brand, category=categories[cat],
                composition=f"{name} {strength}".strip(), dosage_form=form, unit_price=Decimal(price),
                reorder_level=reorder, requires_prescription=rx,
            )
            med.popularity = pop
            meds.append(med)
        return meds

    def _batches_and_orders(self, rng, medicines, suppliers, staff, today, days):
        counter = 1000
        for med in medicines:
            supplier = rng.choice(suppliers)
            low = med.name in LOW_STOCK_DEMO
            plans = []
            # An old batch received before the sales history starts.
            plans.append(("old", today - timedelta(days=days + rng.randint(20, 90))))
            # A mid-period restock.
            plans.append(("mid", today - timedelta(days=rng.randint(25, days - 10))))
            if not low and rng.random() < 0.6:
                plans.append(("recent", today - timedelta(days=rng.randint(1, 20))))
            if not low and rng.random() < 0.45:
                # Short-dated stock bought cheap recently: still on the shelf, expiring soon.
                plans.append(("near", today - timedelta(days=rng.randint(4, 14))))

            for kind, received in plans:
                counter += 1
                qty = self._batch_qty(rng, med, kind, low, days, (today - received).days)
                cost = (med.unit_price * Decimal(str(rng.uniform(0.58, 0.74)))).quantize(Decimal("0.01"))
                expiry = self._expiry(rng, kind, today)
                # Typical shelf life is 2-3 years; manufactured before it was received.
                mfg = min(received - timedelta(days=rng.randint(7, 60)),
                          expiry - timedelta(days=rng.randint(540, 1095)))

                po = PurchaseOrder.objects.create(
                    supplier=supplier, order_date=received - timedelta(days=rng.randint(2, 6)),
                    expected_date=received, received_date=received,
                    status=PurchaseOrder.Status.RECEIVED, created_by=staff,
                )
                PurchaseOrderItem.objects.create(purchase_order=po, medicine=med, quantity=qty, unit_cost=cost)
                Batch.objects.create(
                    medicine=med, supplier=supplier, purchase_order=po,
                    batch_number=f"{med.brand[:3].upper() or 'GEN'}{received:%y%m}{counter}",
                    quantity_received=qty, quantity_available=qty, cost_price=cost,
                    mfg_date=mfg, expiry_date=expiry, received_date=received,
                )

        # A few pending orders so the purchase-order screen isn't empty.
        for _ in range(3):
            po = PurchaseOrder.objects.create(
                supplier=rng.choice(suppliers), order_date=today - timedelta(days=rng.randint(0, 3)),
                expected_date=today + timedelta(days=rng.randint(2, 7)), created_by=staff,
                notes="Monthly restock",
            )
            for med in rng.sample(medicines, 3):
                PurchaseOrderItem.objects.create(
                    purchase_order=po, medicine=med, quantity=rng.choice([50, 100, 150, 200]),
                    unit_cost=(med.unit_price * Decimal("0.65")).quantize(Decimal("0.01")),
                )

    @staticmethod
    def _batch_qty(rng, med, kind, low, days, age):
        # Each popularity point sells roughly 0.5 units/day; size batches around that.
        base = max(30, int(med.popularity * days * 0.35))
        if kind == "near":
            # FEFO sells this first, so leave 15-60 units unsold for the expiry alerts.
            return int(med.popularity * age * 0.55) + rng.randint(15, 60)
        if low:
            return max(10, int(med.reorder_level * (0.9 if kind == "old" else 0.5)))
        if kind == "old":
            return rng.randint(int(base * 0.8), int(base * 1.2))
        return rng.randint(int(base * 0.6), int(base * 1.0))

    @staticmethod
    def _expiry(rng, kind, today):
        roll = rng.random()
        if kind == "near":
            return today + timedelta(days=rng.randint(5, 85))
        if kind == "old":
            # Old stock: some already expired, some expiring soon → expiry alerts.
            if roll < 0.30:
                expiry = today - timedelta(days=rng.randint(3, 45))
            elif roll < 0.55:
                expiry = today + timedelta(days=rng.randint(3, 30))
            elif roll < 0.75:
                expiry = today + timedelta(days=rng.randint(31, 90))
            else:
                expiry = today + timedelta(days=rng.randint(91, 240))
        else:
            expiry = today + timedelta(days=rng.randint(150, 720))
        return expiry

    def _write_offs(self, rng, staff, today):
        """Clear about half of the expired batches, as a storekeeper would have."""
        tz = timezone.get_current_timezone()
        expired = list(Batch.objects.filter(expiry_date__lt=today, quantity_available__gt=0))
        for batch in rng.sample(expired, k=len(expired) // 2):
            when = min(today, batch.expiry_date + timedelta(days=rng.randint(1, 5)))
            StockWriteOff.objects.create(
                batch=batch, quantity=batch.quantity_available, cost_value=batch.quantity_available * batch.cost_price,
                reason=StockWriteOff.Reason.EXPIRED, created_by=staff,
                created_at=datetime.combine(when, time(19, 30), tzinfo=tz),
            )
            batch.quantity_available = 0
            batch.save(update_fields=["quantity_available"])

    def _sales(self, rng, medicines, users, today, days):
        weights = [m.popularity for m in medicines]
        tz = timezone.get_current_timezone()
        sellers = [users["pharmacist"], users["pharmacist"], users["admin"]]
        bills = 0
        now = timezone.now()
        for offset in range(days, -1, -1):
            day = today - timedelta(days=offset)
            # Busier on weekends, slight growth trend over time.
            n_bills = int(rng.randint(14, 26) * (1.25 if day.weekday() >= 5 else 1.0) * (0.85 + 0.3 * (days - offset) / days))
            for _ in range(n_bills):
                hour = rng.choices(range(9, 22), weights=[3, 5, 6, 5, 4, 3, 3, 4, 6, 7, 7, 5, 3])[0]
                created = datetime.combine(day, time(hour, rng.randint(0, 59), rng.randint(0, 59)), tzinfo=tz)
                if created > now:
                    continue
                picks = {}
                for med in rng.choices(medicines, weights=weights, k=rng.choices([1, 2, 3, 4], [40, 35, 18, 7])[0]):
                    picks[med.pk] = (med, rng.choices([1, 2, 3, 5], [55, 28, 12, 5])[0])
                needs_rx = any(m.requires_prescription for m, _ in picks.values())
                subtotal = sum(m.unit_price * q for m, q in picks.values())
                discount = (subtotal * Decimal("0.05")).quantize(Decimal("0.01")) if subtotal > 800 and rng.random() < 0.5 else 0
                try:
                    create_sale(
                        items=[{"medicine": m, "quantity": q} for m, q in picks.values()],
                        user=rng.choice(sellers),
                        customer_name=rng.choice(CUSTOMERS),
                        customer_phone=f"+91 9{rng.randint(100000000, 999999999)}" if rng.random() < 0.4 else "",
                        doctor_name=rng.choice(DOCTORS) if needs_rx else "",
                        payment_method=rng.choices(["UPI", "CASH", "CARD"], [55, 35, 10])[0],
                        discount=discount,
                        created_at=created,
                    )
                    bills += 1
                except StockError:
                    continue  # medicine ran out that day, just like real life
            if offset % 15 == 0:
                self.stdout.write(f"  sales generated up to {day}")
        return bills
