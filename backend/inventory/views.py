from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import connection, transaction
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Min, Q, Sum
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView

from . import metrics
from .models import Batch, Category, Medicine, PurchaseOrder, Sale, SaleItem, StockWriteOff, Supplier
from .permissions import PHARMACIST, STORE_STAFF, IsAdminRole, RolePermission
from .serializers import (
    BatchSerializer, CategorySerializer, MedicineSerializer, PurchaseOrderSerializer,
    ReceivePurchaseOrderSerializer, SaleCreateSerializer, SaleSerializer, SupplierSerializer,
    UserCreateSerializer, UserSerializer,
)
from .services import StockError, create_sale, receive_purchase_order

MONEY = DecimalField(max_digits=14, decimal_places=2)


# ---------------------------------------------------------------- auth / misc

class LoginView(TokenObtainPairView):
    """JWT login that also feeds the login-attempts metric."""

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        metrics.LOGIN_ATTEMPTS.labels(result="success" if response.status_code == 200 else "failure").inc()
        return response


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request):
    return Response(UserSerializer(request.user).data)


@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    return Response({"status": "ok", "time": timezone.now()})


class UserViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, mixins.UpdateModelMixin,
                  viewsets.GenericViewSet):
    queryset = User.objects.order_by("username").prefetch_related("groups")
    permission_classes = [IsAdminRole]

    def get_serializer_class(self):
        return UserCreateSerializer if self.action == "create" else UserSerializer


# ---------------------------------------------------------------- catalogue

class CategoryViewSet(viewsets.ModelViewSet):
    serializer_class = CategorySerializer
    permission_classes = [RolePermission]
    write_roles = (PHARMACIST,)
    pagination_class = None
    search_fields = ["name"]

    def get_queryset(self):
        return Category.objects.annotate(medicine_count=Count("medicines"))


class SupplierViewSet(viewsets.ModelViewSet):
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer
    permission_classes = [RolePermission]
    write_roles = (STORE_STAFF,)
    search_fields = ["name", "contact_person", "phone", "email", "gstin"]


class MedicineViewSet(viewsets.ModelViewSet):
    serializer_class = MedicineSerializer
    permission_classes = [RolePermission]
    write_roles = (PHARMACIST,)
    filterset_fields = ["category", "dosage_form", "requires_prescription", "is_active"]
    search_fields = ["name", "brand", "composition"]
    ordering_fields = ["name", "unit_price", "stock", "nearest_expiry"]

    def get_queryset(self):
        today = timezone.localdate()
        sellable = Q(batches__expiry_date__gte=today, batches__quantity_available__gt=0)
        qs = (
            Medicine.objects.select_related("category")
            .annotate(
                stock=Coalesce(Sum("batches__quantity_available", filter=sellable), 0),
                nearest_expiry=Min("batches__expiry_date", filter=sellable),
            )
            .order_by("name", "id")
        )
        if self.request.query_params.get("low_stock") in ("1", "true"):
            qs = qs.filter(stock__lt=F("reorder_level"), is_active=True)
        if self.request.query_params.get("in_stock") in ("1", "true"):
            qs = qs.filter(stock__gt=0)
        return qs

    def destroy(self, request, *args, **kwargs):
        medicine = self.get_object()
        if medicine.batches.exists():
            # Keep history intact: deactivate instead of deleting.
            medicine.is_active = False
            medicine.save(update_fields=["is_active"])
            return Response({"detail": "Medicine has stock history, so it was deactivated instead."})
        return super().destroy(request, *args, **kwargs)


class BatchViewSet(viewsets.ModelViewSet):
    serializer_class = BatchSerializer
    permission_classes = [RolePermission]
    write_roles = (STORE_STAFF,)
    filterset_fields = ["medicine", "supplier", "purchase_order"]
    search_fields = ["batch_number", "medicine__name", "medicine__brand"]
    ordering_fields = ["expiry_date", "quantity_available", "received_date"]

    def get_queryset(self):
        qs = Batch.objects.select_related("medicine", "supplier")
        params = self.request.query_params
        today = timezone.localdate()
        status_filter = params.get("status")
        if status_filter == "expired":
            qs = qs.filter(expiry_date__lt=today)
        elif status_filter == "critical":
            qs = qs.filter(expiry_date__gte=today, expiry_date__lte=today + timedelta(days=30))
        elif status_filter == "warning":
            qs = qs.filter(expiry_date__gt=today + timedelta(days=30), expiry_date__lte=today + timedelta(days=90))
        elif status_filter == "ok":
            qs = qs.filter(expiry_date__gt=today + timedelta(days=90))
        if params.get("expiring_within"):
            days = int(params["expiring_within"])
            qs = qs.filter(expiry_date__gte=today, expiry_date__lte=today + timedelta(days=days))
        if params.get("in_stock") in ("1", "true"):
            qs = qs.filter(quantity_available__gt=0)
        return qs

    def destroy(self, request, *args, **kwargs):
        if self.get_object().sale_items.exists():
            return Response({"detail": "This batch has sales against it and cannot be deleted."},
                            status=status.HTTP_400_BAD_REQUEST)
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def write_off(self, request, pk=None):
        """Remove expired/damaged units from a batch (counts as a loss)."""
        batch = self.get_object()
        try:
            qty = int(request.data.get("quantity", batch.quantity_available))
        except (TypeError, ValueError):
            qty = 0
        reason = request.data.get("reason", StockWriteOff.Reason.EXPIRED)
        if qty <= 0 or qty > batch.quantity_available or reason not in StockWriteOff.Reason.values:
            return Response({"detail": "Enter a quantity between 1 and the units left in this batch."},
                            status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            StockWriteOff.objects.create(batch=batch, quantity=qty, cost_value=qty * batch.cost_price,
                                         reason=reason, created_by=request.user)
            batch.quantity_available -= qty
            batch.save(update_fields=["quantity_available"])
        return Response(self.get_serializer(batch).data)


# ---------------------------------------------------------------- sales

class SaleViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                  mixins.DestroyModelMixin, viewsets.GenericViewSet):
    permission_classes = [RolePermission]
    write_roles = (PHARMACIST,)
    filterset_fields = ["payment_method"]
    search_fields = ["invoice_number", "customer_name", "customer_phone", "doctor_name"]
    ordering_fields = ["created_at", "total_amount"]

    def get_queryset(self):
        qs = Sale.objects.select_related("sold_by").annotate(item_count=Count("items"))
        params = self.request.query_params
        if params.get("date_from"):
            qs = qs.filter(created_at__date__gte=params["date_from"])
        if params.get("date_to"):
            qs = qs.filter(created_at__date__lte=params["date_to"])
        if self.action == "retrieve":
            qs = qs.prefetch_related("items__medicine", "items__batch")
        return qs

    def get_serializer_class(self):
        return SaleCreateSerializer if self.action == "create" else SaleSerializer

    def create(self, request, *args, **kwargs):
        serializer = SaleCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            sale = create_sale(
                items=data["items"], user=request.user,
                customer_name=data.get("customer_name", ""), customer_phone=data.get("customer_phone", ""),
                doctor_name=data.get("doctor_name", ""), payment_method=data["payment_method"],
                discount=data.get("discount") or Decimal("0"),
            )
        except StockError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        sale = self.get_queryset().prefetch_related("items__medicine", "items__batch").get(pk=sale.pk)
        return Response(SaleSerializer(sale).data, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        """Cancel a bill. The DELETE trigger puts the units back into their batches."""
        sale = self.get_object()
        if timezone.now() - sale.created_at > timedelta(hours=24):
            return Response({"detail": "Bills older than 24 hours cannot be cancelled."},
                            status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            sale.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------- purchasing

class PurchaseOrderViewSet(viewsets.ModelViewSet):
    serializer_class = PurchaseOrderSerializer
    permission_classes = [RolePermission]
    write_roles = (STORE_STAFF,)
    filterset_fields = ["status", "supplier"]
    search_fields = ["supplier__name", "notes"]

    def get_queryset(self):
        return PurchaseOrder.objects.select_related("supplier").prefetch_related("items__medicine")

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def destroy(self, request, *args, **kwargs):
        if self.get_object().status == PurchaseOrder.Status.RECEIVED:
            return Response({"detail": "Received purchase orders cannot be deleted."},
                            status=status.HTTP_400_BAD_REQUEST)
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def receive(self, request, pk=None):
        po = self.get_object()
        serializer = ReceivePurchaseOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        batches = {b["item"]: b for b in serializer.validated_data["batches"]}
        try:
            receive_purchase_order(po, batches, serializer.validated_data.get("received_date"))
        except StockError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(self.get_queryset().get(pk=po.pk)).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        po = self.get_object()
        if po.status != PurchaseOrder.Status.PENDING:
            return Response({"detail": "Only pending orders can be cancelled."}, status=status.HTTP_400_BAD_REQUEST)
        po.status = PurchaseOrder.Status.CANCELLED
        po.save(update_fields=["status"])
        return Response(self.get_serializer(po).data)


# ---------------------------------------------------------------- dashboard & alerts

def _batch_row(b):
    return {
        "id": b.id, "medicine": b.medicine_id, "medicine_name": str(b.medicine), "batch_number": b.batch_number,
        "supplier_name": b.supplier.name, "quantity_available": b.quantity_available,
        "expiry_date": b.expiry_date, "days_to_expiry": b.days_to_expiry,
        "stock_value": str(b.quantity_available * b.cost_price),
    }


@api_view(["GET"])
@permission_classes([RolePermission])
def alerts(request):
    today = timezone.localdate()
    batches = Batch.objects.select_related("medicine", "supplier").filter(quantity_available__gt=0)

    expired = batches.filter(expiry_date__lt=today).order_by("expiry_date")
    expiring = batches.filter(expiry_date__gte=today, expiry_date__lte=today + timedelta(days=90)).order_by("expiry_date")

    low = (
        Medicine.objects.filter(is_active=True)
        .annotate(stock=Coalesce(Sum("batches__quantity_available",
                                     filter=Q(batches__expiry_date__gte=today)), 0))
        .filter(stock__lt=F("reorder_level"))
        .select_related("category")
        .order_by("stock", "name")
    )
    return Response({
        "low_stock": [
            {"id": m.id, "name": str(m), "category": m.category.name, "stock": m.stock,
             "reorder_level": m.reorder_level, "shortfall": m.reorder_level - m.stock}
            for m in low
        ],
        "expired": [_batch_row(b) for b in expired],
        "expiring": [_batch_row(b) for b in expiring],
        "counts": {
            "low_stock": len(low),
            "expired": expired.count(),
            "expiring_30": expiring.filter(expiry_date__lte=today + timedelta(days=30)).count(),
            "expiring_60": expiring.filter(expiry_date__lte=today + timedelta(days=60)).count(),
            "expiring_90": expiring.count(),
        },
    })


@api_view(["GET"])
@permission_classes([RolePermission])
def dashboard(request):
    today = timezone.localdate()
    now = timezone.now()
    value_expr = ExpressionWrapper(F("quantity_available") * F("cost_price"), output_field=MONEY)
    live = Batch.objects.filter(quantity_available__gt=0)

    stock_value = live.filter(expiry_date__gte=today).aggregate(v=Coalesce(Sum(value_expr), Decimal("0")))["v"]
    expired_value = live.filter(expiry_date__lt=today).aggregate(v=Coalesce(Sum(value_expr), Decimal("0")))["v"]
    written_off = StockWriteOff.objects.filter(created_at__gte=now - timedelta(days=30)).aggregate(
        v=Coalesce(Sum("cost_value"), Decimal("0")))["v"]

    sales_today = Sale.objects.filter(created_at__date=today).aggregate(
        revenue=Coalesce(Sum("total_amount"), Decimal("0")), bills=Count("id"))

    start = today - timedelta(days=13)
    daily = {
        row["day"]: row
        for row in Sale.objects.filter(created_at__date__gte=start)
        .annotate(day=TruncDate("created_at")).values("day")
        .annotate(revenue=Sum("total_amount"), bills=Count("id"))
    }
    trend = []
    for i in range(14):
        day = start + timedelta(days=i)
        row = daily.get(day, {})
        trend.append({"date": day, "revenue": str(row.get("revenue") or 0), "bills": row.get("bills", 0)})

    top = (
        SaleItem.objects.filter(sale__created_at__gte=now - timedelta(days=30))
        .values("medicine__name", "medicine__strength")
        .annotate(units=Sum("quantity"), revenue=Sum("line_total"))
        .order_by("-units")[:5]
    )
    by_category = (
        live.filter(expiry_date__gte=today)
        .values("medicine__category__name")
        .annotate(value=Sum(value_expr))
        .order_by("-value")
    )
    low_stock = (
        Medicine.objects.filter(is_active=True)
        .annotate(stock=Coalesce(Sum("batches__quantity_available", filter=Q(batches__expiry_date__gte=today)), 0))
        .filter(stock__lt=F("reorder_level")).count()
    )
    return Response({
        "medicines": Medicine.objects.filter(is_active=True).count(),
        "stock_value": str(stock_value),
        "expired_value": str(expired_value),
        "written_off_30d": str(written_off),
        "revenue_today": str(sales_today["revenue"]),
        "bills_today": sales_today["bills"],
        "low_stock": low_stock,
        "expiring_30": live.filter(expiry_date__gte=today, expiry_date__lte=today + timedelta(days=30)).count(),
        "pending_orders": PurchaseOrder.objects.filter(status=PurchaseOrder.Status.PENDING).count(),
        "sales_trend": trend,
        "top_medicines": [
            {"name": f"{t['medicine__name']} {t['medicine__strength']}".strip(), "units": t["units"],
             "revenue": str(t["revenue"])} for t in top
        ],
        "stock_by_category": [
            {"category": c["medicine__category__name"], "value": str(c["value"])} for c in by_category
        ],
    })
