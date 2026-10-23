from django.contrib import admin

from .models import Batch, Category, Medicine, PurchaseOrder, PurchaseOrderItem, Sale, SaleItem, StockWriteOff, Supplier


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    search_fields = ["name"]


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ["name", "contact_person", "phone", "email", "gstin"]
    search_fields = ["name", "contact_person", "gstin"]


class BatchInline(admin.TabularInline):
    model = Batch
    extra = 0
    fields = ["batch_number", "supplier", "quantity_available", "cost_price", "expiry_date"]


@admin.register(Medicine)
class MedicineAdmin(admin.ModelAdmin):
    list_display = ["name", "strength", "brand", "category", "unit_price", "reorder_level", "requires_prescription", "is_active"]
    list_filter = ["category", "dosage_form", "requires_prescription", "is_active"]
    search_fields = ["name", "brand", "composition"]
    inlines = [BatchInline]


@admin.register(Batch)
class BatchAdmin(admin.ModelAdmin):
    list_display = ["batch_number", "medicine", "supplier", "quantity_available", "quantity_received", "expiry_date"]
    list_filter = ["supplier", "expiry_date"]
    search_fields = ["batch_number", "medicine__name"]
    date_hierarchy = "expiry_date"


class PurchaseOrderItemInline(admin.TabularInline):
    model = PurchaseOrderItem
    extra = 0


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ["__str__", "supplier", "order_date", "status"]
    list_filter = ["status", "supplier"]
    inlines = [PurchaseOrderItemInline]


class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 0
    readonly_fields = ["medicine", "batch", "quantity", "unit_price", "line_total"]
    can_delete = False


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ["invoice_number", "customer_name", "total_amount", "payment_method", "created_at", "sold_by"]
    list_filter = ["payment_method", "created_at"]
    search_fields = ["invoice_number", "customer_name", "customer_phone"]
    inlines = [SaleItemInline]
    readonly_fields = ["invoice_number", "subtotal", "total_amount"]


@admin.register(StockWriteOff)
class StockWriteOffAdmin(admin.ModelAdmin):
    list_display = ["batch", "quantity", "cost_value", "reason", "created_by", "created_at"]
    list_filter = ["reason"]
