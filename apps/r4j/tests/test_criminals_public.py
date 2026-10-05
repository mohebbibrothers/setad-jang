"""
Tests — apps.r4j public criminal endpoints (Phase R4J.2)

این تست‌ها رفتار endpointهای عمومی را verify می‌کنند:
- لیست فقط شامل published + active
- detail با id یا slug
- visibility map اعمال می‌شود (national_code default hidden)
- override per-criminal کار می‌کند

اصول طراحی:
- هیچ business logic فراتر از scope این فاز تست نمی‌شود.
- request.user همیشه anonymous است.
"""

from __future__ import annotations

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.r4j.models import R4JCriminalFieldVisibility
from tests.factories.r4j import R4JCriminalFactory

pytestmark = [pytest.mark.django_db]


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


# ============================================================
# List endpoint
# ============================================================


class TestPublicCriminalList:
    """رفتار list endpoint عمومی."""

    def test_list_returns_only_published_criminals(self, api_client) -> None:
        published = R4JCriminalFactory(
            first_name="منتشر",
            last_name="شده",
            is_published=True,
        )
        draft = R4JCriminalFactory(
            first_name="دراف",
            last_name="ت",
            is_published=False,
        )

        # publish manually تا published_at هم set شود
        published.publish()

        response = api_client.get("/api/v1/r4j/criminals/")
        assert response.status_code == status.HTTP_200_OK

        results = response.data["data"]["results"]
        ids = [r["id"] for r in results]
        assert published.pk in ids
        assert draft.pk not in ids

    def test_list_filter_by_country(self, api_client) -> None:
        a = R4JCriminalFactory(country="USA")
        b = R4JCriminalFactory(country="ایران")
        a.publish()
        b.publish()

        response = api_client.get("/api/v1/r4j/criminals/?country=USA")
        assert response.status_code == status.HTTP_200_OK

        results = response.data["data"]["results"]
        ids = [r["id"] for r in results]
        assert a.pk in ids
        assert b.pk not in ids

    def test_list_search_in_name(self, api_client) -> None:
        a = R4JCriminalFactory(first_name="Donald", last_name="Trump")
        b = R4JCriminalFactory(first_name="Joseph", last_name="Biden")
        a.publish()
        b.publish()

        response = api_client.get("/api/v1/r4j/criminals/?search=trump")
        assert response.status_code == status.HTTP_200_OK

        results = response.data["data"]["results"]
        ids = [r["id"] for r in results]
        assert a.pk in ids
        assert b.pk not in ids

    def test_list_ordering_by_total_bounty_desc(self, api_client) -> None:
        low = R4JCriminalFactory(total_bounty_toman=100_000)
        high = R4JCriminalFactory(total_bounty_toman=900_000)
        mid = R4JCriminalFactory(total_bounty_toman=500_000)
        low.publish()
        high.publish()
        mid.publish()

        response = api_client.get("/api/v1/r4j/criminals/?ordering=-total_bounty_toman")
        assert response.status_code == status.HTTP_200_OK

        results = response.data["data"]["results"]
        ids = [r["id"] for r in results]
        assert ids == [high.pk, mid.pk, low.pk]

    def test_list_ordering_by_total_bounty_asc(self, api_client) -> None:
        low = R4JCriminalFactory(total_bounty_toman=100_000)
        high = R4JCriminalFactory(total_bounty_toman=900_000)
        low.publish()
        high.publish()

        response = api_client.get("/api/v1/r4j/criminals/?ordering=total_bounty_toman")
        assert response.status_code == status.HTTP_200_OK

        results = response.data["data"]["results"]
        ids = [r["id"] for r in results]
        assert ids == [low.pk, high.pk]

    def test_list_ordering_ignores_unsupported_field(self, api_client) -> None:
        a = R4JCriminalFactory()
        a.publish()

        response = api_client.get("/api/v1/r4j/criminals/?ordering=national_code")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["count"] == 1


# ============================================================
# Detail endpoint
# ============================================================


class TestPublicCriminalDetail:
    """رفتار detail endpoint عمومی."""

    def test_detail_by_id(self, api_client) -> None:
        criminal = R4JCriminalFactory()
        criminal.publish()

        response = api_client.get(f"/api/v1/r4j/criminals/{criminal.pk}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["id"] == criminal.pk

    def test_detail_by_slug(self, api_client) -> None:
        criminal = R4JCriminalFactory()
        criminal.publish()

        response = api_client.get(f"/api/v1/r4j/criminals/{criminal.slug}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["slug"] == criminal.slug

    def test_detail_not_found_returns_404(self, api_client) -> None:
        response = api_client.get("/api/v1/r4j/criminals/99999/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_unpublished_criminal_returns_404(self, api_client) -> None:
        criminal = R4JCriminalFactory(is_published=False)
        response = api_client.get(f"/api/v1/r4j/criminals/{criminal.pk}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_national_code_hidden_by_default(self, api_client) -> None:
        """فیلد national_code به‌صورت default برای public hidden است."""
        criminal = R4JCriminalFactory(national_code="0012345678")
        criminal.publish()

        response = api_client.get(f"/api/v1/r4j/criminals/{criminal.pk}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["national_code"] is None

    def test_national_code_revealed_by_visibility_override(self, api_client) -> None:
        """ادمین می‌تواند per-criminal آن را عمومی کند."""
        criminal = R4JCriminalFactory(national_code="0012345678")
        criminal.publish()

        R4JCriminalFieldVisibility.objects.create(
            criminal=criminal,
            field_name="national_code",
            is_public=True,
        )

        response = api_client.get(f"/api/v1/r4j/criminals/{criminal.pk}/")
        assert response.data["data"]["national_code"] == "0012345678"
