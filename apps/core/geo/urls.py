"""مسیرهای عمومیِ جغرافیا (namespace: geo)."""

from django.urls import path

from apps.core.geo import views

app_name = "geo"

urlpatterns = [
    path("provinces/", views.GeoProvinceListView.as_view(), name="province-list"),
    path("cities/", views.GeoCityListView.as_view(), name="city-list"),
    path("localities/", views.GeoLocalityListView.as_view(), name="locality-list"),
]
