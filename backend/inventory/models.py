"""
PharmaTrack data model (3NF).

    Category 1───* Medicine 1───* Batch *───1 Supplier
                      │             │
                      │             └──* SaleItem *───1 Sale
                      └──* PurchaseOrderItem *───1 PurchaseOrder *───1 Supplier

Stock is tracked per *batch* because every batch has its own expiry date.
A medicine's stock is never stored; it is derived from its batches (see the
`v_medicine_stock` view in migration 0002) so it can never drift out of sync.
Batch quantities are decremented by a PostgreSQL trigger when a SaleItem is
inserted, so the rule holds even for rows written outside Django.
"""
from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class Category(models.Model):
    name = models.CharField(max_length=80, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


class Supplier(models.Model):
    name = models.CharField(max_length=150, unique=True)
    contact_person = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    gstin = models.CharField("GSTIN", max_length=15, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Medicine(models.Model):
    class DosageForm(models.TextChoices):
        TABLET = "TABLET", "Tablet"
        CAPSULE = "CAPSULE", "Capsule"
        SYRUP = "SYRUP", "Syrup"
        INJECTION = "INJECTION", "Injection"
        OINTMENT = "OINTMENT", "Ointment"
        DROPS = "DROPS", "Drops"
        INHALER = "INHALER", "Inhaler"
        POWDER = "POWDER", "Powder"
        OTHER = "OTHER", "Other"

    name = models.CharField(max_length=150)
    brand = models.CharField(max_length=100, blank=True)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="medicines")
    composition = models.CharField(max_length=255, blank=True, help_text="Active ingredients, e.g. Paracetamol 500 mg")
    dosage_form = models.CharField(max_length=20, choices=DosageForm.choices, default=DosageForm.TABLET)
    strength = models.CharField(max_length=50, blank=True)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, help_text="Selling price per unit (strip/bottle)")
    reorder_level = models.PositiveIntegerField(default=20, help_text="Raise a low-stock alert below this quantity")
    requires_prescription = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["name", "brand", "strength"], name="uniq_medicine_name_brand_strength"),
            models.CheckConstraint(condition=Q(unit_price__gte=0), name="medicine_price_non_negative"),
        ]

    def __str__(self):
        return f"{self.name} {self.strength}".strip()


class PurchaseOrder(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        RECEIVED = "RECEIVED", "Received"
        CANCELLED = "CANCELLED", "Cancelled"

    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="purchase_orders")
    order_date = models.DateField(default=timezone.localdate)
    expected_date = models.DateField(null=True, blank=True)
    received_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-order_date", "-id"]

    def __str__(self):
        return f"PO-{self.pk:05d}" if self.pk else "PO (unsaved)"


class PurchaseOrderItem(models.Model):
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="items")
    medicine = models.ForeignKey(Medicine, on_delete=models.PROTECT, related_name="purchase_items")
    quantity = models.PositiveIntegerField()
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(quantity__gt=0), name="po_item_qty_positive")]

    @property
    def line_total(self):
        return self.quantity * self.unit_cost


class Batch(models.Model):
    medicine = models.ForeignKey(Medicine, on_delete=models.PROTECT, related_name="batches")
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="batches")
    purchase_order = models.ForeignKey(
        PurchaseOrder, on_delete=models.SET_NULL, null=True, blank=True, related_name="batches"
    )
    batch_number = models.CharField(max_length=50)
    quantity_received = models.PositiveIntegerField()
    quantity_available = models.PositiveIntegerField()
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, help_text="Purchase cost per unit")
    mfg_date = models.DateField("manufacture date")
    expiry_date = models.DateField(db_index=True)
    received_date = models.DateField(default=timezone.localdate)

    class Meta:
        ordering = ["expiry_date"]
        verbose_name_plural = "batches"
        constraints = [
            models.UniqueConstraint(fields=["medicine", "batch_number"], name="uniq_batch_per_medicine"),
            models.CheckConstraint(condition=Q(expiry_date__gt=models.F("mfg_date")), name="batch_expiry_after_mfg"),
            models.CheckConstraint(
                condition=Q(quantity_available__lte=models.F("quantity_received")), name="batch_available_lte_received"
            ),
        ]
        indexes = [models.Index(fields=["medicine", "expiry_date"], name="batch_medicine_expiry_idx")]

    def __str__(self):
        return f"{self.medicine} / {self.batch_number}"

    @property
    def days_to_expiry(self):
        return (self.expiry_date - timezone.localdate()).days

    @property
    def expiry_status(self):
        days = self.days_to_expiry
        if days < 0:
            return "EXPIRED"
        if days <= 30:
            return "CRITICAL"
        if days <= 90:
            return "WARNING"
        return "OK"


class Sale(models.Model):
    class PaymentMethod(models.TextChoices):
        CASH = "CASH", "Cash"
        UPI = "UPI", "UPI"
        CARD = "CARD", "Card"

    invoice_number = models.CharField(max_length=30, unique=True, blank=True)
    customer_name = models.CharField(max_length=100, blank=True)
    customer_phone = models.CharField(max_length=15, blank=True)
    doctor_name = models.CharField(max_length=100, blank=True, help_text="Prescribing doctor, for Rx medicines")
    payment_method = models.CharField(max_length=10, choices=PaymentMethod.choices, default=PaymentMethod.CASH)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    sold_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(condition=Q(discount__gte=0), name="sale_discount_non_negative"),
            models.CheckConstraint(condition=Q(total_amount__gte=0), name="sale_total_non_negative"),
        ]

    def __str__(self):
        return self.invoice_number or f"Sale #{self.pk}"


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="items")
    batch = models.ForeignKey(Batch, on_delete=models.PROTECT, related_name="sale_items")
    # Denormalised from batch for fast reporting (Grafana "top medicines" etc.).
    medicine = models.ForeignKey(Medicine, on_delete=models.PROTECT, related_name="sale_items")
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    line_total = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(quantity__gt=0), name="sale_item_qty_positive")]
        indexes = [models.Index(fields=["medicine"], name="saleitem_medicine_idx")]

    def __str__(self):
        return f"{self.quantity} × {self.medicine}"


class StockWriteOff(models.Model):
    """Units removed from a batch without being sold (expired, damaged). Counted as loss."""

    class Reason(models.TextChoices):
        EXPIRED = "EXPIRED", "Expired"
        DAMAGED = "DAMAGED", "Damaged"
        OTHER = "OTHER", "Other"

    batch = models.ForeignKey(Batch, on_delete=models.PROTECT, related_name="write_offs")
    quantity = models.PositiveIntegerField()
    cost_value = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.CharField(max_length=10, choices=Reason.choices, default=Reason.EXPIRED)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.CheckConstraint(condition=Q(quantity__gt=0), name="writeoff_qty_positive")]
