from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from . import views

router = DefaultRouter()
router.register("categories", views.CategoryViewSet, basename="category")
router.register("suppliers", views.SupplierViewSet, basename="supplier")
router.register("medicines", views.MedicineViewSet, basename="medicine")
router.register("batches", views.BatchViewSet, basename="batch")
router.register("sales", views.SaleViewSet, basename="sale")
router.register("purchase-orders", views.PurchaseOrderViewSet, basename="purchase-order")
router.register("users", views.UserViewSet, basename="user")

urlpatterns = [
    path("auth/login/", views.LoginView.as_view(), name="login"),
    path("auth/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("auth/me/", views.me, name="me"),
    path("health/", views.health, name="health"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("alerts/", views.alerts, name="alerts"),
    path("", include(router.urls)),
]
