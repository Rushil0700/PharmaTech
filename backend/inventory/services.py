"""
Business logic kept out of the views so it can be unit-tested and reused by
management commands (seed_data, simulate_sales).
"""
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from . import metrics
from .models import Batch, Medicine, PurchaseOrder, Sale, SaleItem


class StockError(Exception):
    """Raised when a sale cannot be fulfilled from non-expired stock."""


def available_batches(medicine, on_date=None):
    """Non-expired batches with stock, earliest expiry first (FEFO order)."""
    on_date = on_date or timezone.localdate()
    return Batch.objects.filter(
        medicine=medicine, quantity_available__gt=0, expiry_date__gte=on_date, received_date__lte=on_date
    ).order_by("expiry_date", "id")


@transaction.atomic
def create_sale(*, items, user=None, customer_name="", customer_phone="", doctor_name="",
                payment_method=Sale.PaymentMethod.CASH, discount=Decimal("0"), created_at=None):
    """
    Create a bill and allocate stock using FEFO (First Expiry, First Out).

    `items` is a list of {"medicine": Medicine | id, "quantity": int}. A requested
    quantity may be split across several batches. Batch rows are locked with
    SELECT ... FOR UPDATE so two counters selling the same medicine at the same
    moment cannot oversell. The actual decrement is done by the database trigger
    `trg_sale_item_stock` (see migration 0002).
    """
    if not items:
        raise StockError("A bill needs at least one item.")

    created_at = created_at or timezone.now()
    sale_date = timezone.localdate(created_at)
    sale = Sale.objects.create(
        customer_name=customer_name,
        customer_phone=customer_phone,
        doctor_name=doctor_name,
        payment_method=payment_method,
        sold_by=user,
        created_at=created_at,
    )

    # Merge duplicate lines for the same medicine.
    wanted = {}
    for item in items:
        med = item["medicine"]
        med_id = med.pk if isinstance(med, Medicine) else int(med)
        wanted[med_id] = wanted.get(med_id, 0) + int(item["quantity"])

    medicines = Medicine.objects.in_bulk(list(wanted))
    subtotal = Decimal("0")
    units = 0
    for med_id, qty in wanted.items():
        medicine = medicines.get(med_id)
        if medicine is None or not medicine.is_active:
            raise StockError(f"Medicine #{med_id} does not exist or is inactive.")
        if qty <= 0:
            raise StockError(f"Quantity for {medicine} must be positive.")
        if medicine.requires_prescription and not doctor_name:
            raise StockError(f"{medicine} is a prescription medicine; enter the doctor's name.")

        remaining = qty
        for batch in available_batches(medicine, sale_date).select_for_update():
            if remaining == 0:
                break
            take = min(remaining, batch.quantity_available)
            line_total = medicine.unit_price * take
            SaleItem.objects.create(
                sale=sale, batch=batch, medicine=medicine,
                quantity=take, unit_price=medicine.unit_price, line_total=line_total,
            )
            subtotal += line_total
            remaining -= take
        if remaining:
            raise StockError(f"Only {qty - remaining} unit(s) of {medicine} in stock (requested {qty}).")
        units += qty

    discount = Decimal(discount or 0)
    if discount < 0 or discount > subtotal:
        raise StockError("Discount must be between 0 and the bill subtotal.")

    sale.subtotal = subtotal
    sale.discount = discount
    sale.total_amount = subtotal - discount
    sale.invoice_number = f"INV-{sale_date:%Y%m%d}-{sale.pk:05d}"
    sale.save(update_fields=["subtotal", "discount", "total_amount", "invoice_number"])

    metrics.record_sale(sale.total_amount, units, payment_method)
    return sale


@transaction.atomic
def receive_purchase_order(purchase_order, batches, received_date=None):
    """
    Mark a PO as received and turn each line into a stock Batch.

    `batches` maps PurchaseOrderItem id -> {"batch_number", "mfg_date", "expiry_date"}.
    """
    if purchase_order.status != PurchaseOrder.Status.PENDING:
        raise StockError(f"{purchase_order} is already {purchase_order.get_status_display().lower()}.")
    received_date = received_date or timezone.localdate()

    created = []
    for item in purchase_order.items.select_related("medicine"):
        info = batches.get(item.id) or batches.get(str(item.id))
        if not info:
            raise StockError(f"Batch details missing for {item.medicine}.")
        created.append(Batch.objects.create(
            medicine=item.medicine,
            supplier=purchase_order.supplier,
            purchase_order=purchase_order,
            batch_number=info["batch_number"],
            quantity_received=item.quantity,
            quantity_available=item.quantity,
            cost_price=item.unit_cost,
            mfg_date=info["mfg_date"],
            expiry_date=info["expiry_date"],
            received_date=received_date,
        ))
    purchase_order.status = PurchaseOrder.Status.RECEIVED
    purchase_order.received_date = received_date
    purchase_order.save(update_fields=["status", "received_date"])
    return created
