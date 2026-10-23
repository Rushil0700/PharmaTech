from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "PharmaTrack Administration"
admin.site.site_title = "PharmaTrack"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("inventory.urls")),
    # Prometheus scrapes http://backend:8000/metrics (not exposed through nginx).
    path("", include("django_prometheus.urls")),
]
