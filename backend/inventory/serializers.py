from django.contrib.auth.models import Group, User
from django.utils import timezone
from rest_framework import serializers

from .models import Batch, Category, Medicine, PurchaseOrder, PurchaseOrderItem, Sale, SaleItem, Supplier
from .permissions import ROLES, get_role


class UserSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "email", "role", "is_active", "last_login"]

    def get_role(self, obj):
        return get_role(obj)


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)
    role = serializers.ChoiceField(choices=ROLES, write_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "email", "password", "role"]

    def create(self, validated):
        role = validated.pop("role")
        password = validated.pop("password")
        user = User(**validated, is_staff=(role == "Admin"))
        user.set_password(password)
        user.save()
        if role != "Admin":
            user.groups.add(Group.objects.get_or_create(name=role)[0])
        return user

    def to_representation(self, instance):
        return UserSerializer(instance).data


class CategorySerializer(serializers.ModelSerializer):
    medicine_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Category
        fields = ["id", "name", "description", "medicine_count"]


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = ["id", "name", "contact_person", "phone", "email", "address", "gstin", "created_at"]


class MedicineSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    dosage_form_display = serializers.CharField(source="get_dosage_form_display", read_only=True)
    # Annotated in the viewset queryset.
    stock = serializers.IntegerField(read_only=True)
    nearest_expiry = serializers.DateField(read_only=True)
    is_low_stock = serializers.SerializerMethodField()

    class Meta:
        model = Medicine
        fields = [
            "id", "name", "brand", "category", "category_name", "composition", "dosage_form",
            "dosage_form_display", "strength", "unit_price", "reorder_level", "requires_prescription",
            "is_active", "stock", "nearest_expiry", "is_low_stock", "created_at",
        ]

    def get_is_low_stock(self, obj):
        stock = getattr(obj, "stock", None)
        return stock is not None and stock < obj.reorder_level


class BatchSerializer(serializers.ModelSerializer):
    medicine_name = serializers.CharField(source="medicine.__str__", read_only=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    days_to_expiry = serializers.IntegerField(read_only=True)
    expiry_status = serializers.CharField(read_only=True)
    stock_value = serializers.SerializerMethodField()

    class Meta:
        model = Batch
        fields = [
            "id", "medicine", "medicine_name", "supplier", "supplier_name", "purchase_order",
            "batch_number", "quantity_received", "quantity_available", "cost_price", "mfg_date",
            "expiry_date", "received_date", "days_to_expiry", "expiry_status", "stock_value",
        ]
        read_only_fields = ["purchase_order"]
        extra_kwargs = {"quantity_available": {"required": False}}

    def get_stock_value(self, obj):
        return str(obj.quantity_available * obj.cost_price)

    def validate(self, attrs):
        mfg = attrs.get("mfg_date", getattr(self.instance, "mfg_date", None))
        exp = attrs.get("expiry_date", getattr(self.instance, "expiry_date", None))
        if mfg and exp and exp <= mfg:
            raise serializers.ValidationError({"expiry_date": "Expiry must be after manufacture date."})
        if mfg and mfg > timezone.localdate():
            raise serializers.ValidationError({"mfg_date": "Manufacture date cannot be in the future."})
        received = attrs.get("quantity_received", getattr(self.instance, "quantity_received", 0))
        if self.instance is None:
            attrs.setdefault("quantity_available", received)
        available = attrs.get("quantity_available", getattr(self.instance, "quantity_available", 0))
        if available > received:
            raise serializers.ValidationError({"quantity_available": "Cannot exceed quantity received."})
        return attrs


class SaleItemSerializer(serializers.ModelSerializer):
    medicine_name = serializers.CharField(source="medicine.__str__", read_only=True)
    batch_number = serializers.CharField(source="batch.batch_number", read_only=True)
    expiry_date = serializers.DateField(source="batch.expiry_date", read_only=True)

    class Meta:
        model = SaleItem
        fields = ["id", "medicine", "medicine_name", "batch", "batch_number", "expiry_date",
                  "quantity", "unit_price", "line_total"]


class SaleSerializer(serializers.ModelSerializer):
    items = SaleItemSerializer(many=True, read_only=True)
    sold_by_name = serializers.CharField(source="sold_by.username", read_only=True, default=None)
    item_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Sale
        fields = ["id", "invoice_number", "customer_name", "customer_phone", "doctor_name",
                  "payment_method", "subtotal", "discount", "total_amount", "sold_by_name",
                  "created_at", "item_count", "items"]


class SaleLineInput(serializers.Serializer):
    medicine = serializers.PrimaryKeyRelatedField(queryset=Medicine.objects.filter(is_active=True))
    quantity = serializers.IntegerField(min_value=1, max_value=10000)


class SaleCreateSerializer(serializers.Serializer):
    customer_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    customer_phone = serializers.CharField(max_length=15, required=False, allow_blank=True)
    doctor_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    payment_method = serializers.ChoiceField(choices=Sale.PaymentMethod.choices, default=Sale.PaymentMethod.CASH)
    discount = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, default=0, min_value=0)
    items = SaleLineInput(many=True, allow_empty=False)


class PurchaseOrderItemSerializer(serializers.ModelSerializer):
    medicine_name = serializers.CharField(source="medicine.__str__", read_only=True)
    line_total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = PurchaseOrderItem
        fields = ["id", "medicine", "medicine_name", "quantity", "unit_cost", "line_total"]


class PurchaseOrderSerializer(serializers.ModelSerializer):
    items = PurchaseOrderItemSerializer(many=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    po_number = serializers.CharField(source="__str__", read_only=True)
    total_cost = serializers.SerializerMethodField()

    class Meta:
        model = PurchaseOrder
        fields = ["id", "po_number", "supplier", "supplier_name", "order_date", "expected_date",
                  "received_date", "status", "notes", "items", "total_cost", "created_at"]
        read_only_fields = ["status", "received_date"]

    def get_total_cost(self, obj):
        return str(sum((i.line_total for i in obj.items.all()), 0))

    def validate_items(self, items):
        if not items:
            raise serializers.ValidationError("Add at least one medicine.")
        return items

    def create(self, validated):
        items = validated.pop("items")
        po = PurchaseOrder.objects.create(**validated)
        PurchaseOrderItem.objects.bulk_create(PurchaseOrderItem(purchase_order=po, **i) for i in items)
        return po

    def update(self, instance, validated):
        if instance.status != PurchaseOrder.Status.PENDING:
            raise serializers.ValidationError("Only pending purchase orders can be edited.")
        items = validated.pop("items", None)
        for key, value in validated.items():
            setattr(instance, key, value)
        instance.save()
        if items is not None:
            instance.items.all().delete()
            PurchaseOrderItem.objects.bulk_create(PurchaseOrderItem(purchase_order=instance, **i) for i in items)
        return instance


class ReceiveBatchInput(serializers.Serializer):
    item = serializers.IntegerField()
    batch_number = serializers.CharField(max_length=50)
    mfg_date = serializers.DateField()
    expiry_date = serializers.DateField()

    def validate(self, attrs):
        if attrs["expiry_date"] <= attrs["mfg_date"]:
            raise serializers.ValidationError("Expiry must be after manufacture date.")
        return attrs


class ReceivePurchaseOrderSerializer(serializers.Serializer):
    received_date = serializers.DateField(required=False)
    batches = ReceiveBatchInput(many=True, allow_empty=False)
