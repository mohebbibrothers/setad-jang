"""API عمومیِ جغرافیا — منبعِ واحدِ استان/شهر برای فرانت و پنلِ ادمین.

قرارداد (هم‌نام با فیلترهای `kindness_wall`):
  GET /api/v1/geo/provinces/            → [{name, tel_prefix, cities_count}]
  GET /api/v1/geo/cities/?province=…    → {province, cities: [...]}
  GET /api/v1/geo/localities/?province=…→ {province, localities: [...]}

همه AllowAny و بدونِ کوئریِ دیتابیس (دیتاستِ درون‌حافظه) هستند؛ پاسخ با
Cache-Control طولانی کش می‌شود چون دادهٔ تقسیماتِ کشوری سالی یک‌بار عوض می‌شود.
"""

from __future__ import annotations

from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_control
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.geo.dataset import (
    cities_of,
    localities_of,
    normalize_province,
    places_catalog,
)
from apps.core.responses import SuccessResponse

TAG_GEO = "geo"


@method_decorator(cache_control(public=True, max_age=86_400), name="dispatch")
class GeoProvinceListView(APIView):
    """۳۱ استانِ رسمی همراه با شمارِ شهرهای هر استان."""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    @extend_schema(
        operation_id="geo_provinces_list",
        tags=[TAG_GEO],
        summary="فهرست استان‌های رسمی",
        responses={200: None},
    )
    def get(self, request: Request) -> Response:
        """کاتالوگِ سبک (بدونِ شهرها) برای ساختنِ دراپ‌دانِ استان."""
        rows = [
            {
                "name": row["name"],
                "tel_prefix": row["tel_prefix"],
                "cities_count": len(row["cities"]),
            }
            for row in places_catalog()
        ]
        return SuccessResponse(data=rows, message="استان‌ها دریافت شد.")


@method_decorator(cache_control(public=True, max_age=86_400), name="dispatch")
class GeoCityListView(APIView):
    """شهرهای رسمیِ یک استان (برای دراپ‌دانِ وابسته در فرانت و ادمین)."""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    @extend_schema(
        operation_id="geo_cities_list",
        tags=[TAG_GEO],
        summary="شهرهای یک استان",
        parameters=[
            OpenApiParameter(
                name="province",
                location=OpenApiParameter.QUERY,
                required=True,
                type=str,
                description="نامِ رسمیِ استان (مثلاً «تهران»).",
            )
        ],
        responses={200: None, 404: None},
    )
    def get(self, request: Request) -> Response:
        """اگر استان ناشناخته باشد ۴۰۴ صریح می‌دهیم تا فرانت به فهرستِ خالی گمراه نشود."""
        province_raw = (request.query_params.get("province") or "").strip()
        province = normalize_province(province_raw)
        if not province:
            return Response(
                {"success": False, "status_code": 404, "message": "استان یافت نشد.", "data": None},
                status=404,
            )
        return SuccessResponse(
            data={"province": province, "cities": cities_of(province)},
            message="شهرها دریافت شد.",
        )


@method_decorator(cache_control(public=True, max_age=86_400), name="dispatch")
class GeoLocalityListView(APIView):
    """روستا/محله‌های یک استان — فقط اگر دیتاستِ اختیاری متصل باشد."""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    @extend_schema(
        operation_id="geo_localities_list",
        tags=[TAG_GEO],
        summary="روستا/محله‌های یک استان (اختیاری)",
        parameters=[
            OpenApiParameter(
                name="province",
                location=OpenApiParameter.QUERY,
                required=True,
                type=str,
                description="نامِ رسمیِ استان.",
            )
        ],
        responses={200: None, 404: None},
    )
    def get(self, request: Request) -> Response:
        """خالی بودن فهرست یعنی دیتاستِ روستا نصب نیست (نه خطا)."""
        province = normalize_province((request.query_params.get("province") or "").strip())
        if not province:
            return Response(
                {"success": False, "status_code": 404, "message": "استان یافت نشد.", "data": None},
                status=404,
            )
        return SuccessResponse(
            data={"province": province, "localities": localities_of(province)},
            message="روستا/محله‌ها دریافت شد.",
        )
