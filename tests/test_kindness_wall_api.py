"""
Kindness Wall Phase 3 full API layer tests.

Covers public browse, authenticated contact reveal, user listing CRUD/submit,
bookmarks, reports, matches, and admin review/moderation endpoints.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.audit_logs import actions as audit_actions
from apps.kindness_wall.choices import ListingStatus, ListingType, ReportReason, ReportStatus
from apps.kindness_wall.models import (
    KindnessBookmark,
    KindnessContactReveal,
    KindnessListing,
    KindnessListingReport,
    KindnessMatch,
)
from apps.kindness_wall.services import create_listing, submit_listing_for_review
from tests.factories import AdminUserFactory
from tests.factories.kindness_wall import (
    KindnessCategoryFactory,
    KindnessUserFactory,
    PublishedNeedListingFactory,
    PublishedOfferListingFactory,
)

pytestmark = pytest.mark.django_db

_TASK_PATCH_PATH = "apps.audit_logs.tasks.create_audit_log_task"


def _client_for(user) -> APIClient:
    """Return authenticated API client."""
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _make_pending_listing(*, owner=None, category=None) -> KindnessListing:
    """Create pending listing through service workflow."""
    owner = owner or KindnessUserFactory()
    category = category or KindnessCategoryFactory()
    listing = create_listing(
        owner=owner,
        listing_type=ListingType.NEED_HELP,
        category=category,
        title="برنامه نویس فول استک نیاز دارم",
        description="برای سایت خیریه دنبال طراح سایت و برنامه نویس هستم",
    )
    submit_listing_for_review(listing=listing, user=owner)
    return listing


class TestKindnessPublicAPI:
    """Public browse/search/detail behavior."""

    def test_public_listing_list_filters_and_never_exposes_phone(self) -> None:
        category = KindnessCategoryFactory(title="مشاغل")
        published = PublishedNeedListingFactory(
            category=category, title="برنامه نویس لازم دارم", contact_phone_snapshot="+989120000000"
        )
        KindnessListing.objects.create(
            owner=KindnessUserFactory(),
            listing_type=ListingType.NEED_HELP,
            category=category,
            title="پیش نویس",
            description="نباید دیده شود",
            province="تهران",
            city="تهران",
            contact_phone_snapshot="+989120000001",
            owner_full_name_snapshot="کاربر تست",
            status=ListingStatus.DRAFT,
        )

        response = APIClient().get(reverse("kindness_wall:listing-list"), data={"search": "برنامه"})

        assert response.status_code == status.HTTP_200_OK
        results = response.data["data"]["results"]
        assert len(results) == 1
        assert results[0]["id"] == published.pk
        assert "contact_phone_snapshot" not in results[0]

    def test_public_detail_has_contact_available_but_not_phone(self) -> None:
        listing = PublishedOfferListingFactory(contact_phone_snapshot="+989120000000")

        response = APIClient().get(
            reverse("kindness_wall:listing-detail", kwargs={"slug": listing.slug})
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["contact_available"] is True
        assert "contact_phone_snapshot" not in response.data["data"]


class TestKindnessContactRevealAPI:
    """Contact reveal must be authenticated and audited."""

    def test_anonymous_cannot_reveal_contact(self) -> None:
        listing = PublishedNeedListingFactory()

        response = APIClient().post(
            reverse("kindness_wall:listing-reveal-contact", kwargs={"slug": listing.slug})
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert KindnessContactReveal.objects.count() == 0

    def test_authenticated_user_can_reveal_contact_and_audit_dispatches(self) -> None:
        listing = PublishedNeedListingFactory(contact_phone_snapshot="+989120000000")
        viewer = KindnessUserFactory()

        with patch(_TASK_PATCH_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = _client_for(viewer).post(
                reverse("kindness_wall:listing-reveal-contact", kwargs={"slug": listing.slug})
            )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["phone_number"] == "+989120000000"
        assert KindnessContactReveal.objects.filter(viewer=viewer, listing=listing).exists()
        assert mock_task.delay.call_args.kwargs["action"] == audit_actions.KINDNESS_CONTACT_REVEALED


class TestKindnessUserListingAPI:
    """Owner listing CRUD and submit behavior."""

    def test_user_can_create_update_and_submit_listing(self) -> None:
        user = KindnessUserFactory()
        category = KindnessCategoryFactory(title="مشاغل")
        client = _client_for(user)

        with patch(_TASK_PATCH_PATH) as mock_task:
            mock_task.delay = MagicMock()
            create_response = client.post(
                reverse("kindness_wall:user-listing-list-create"),
                data={
                    "listing_type": ListingType.NEED_HELP,
                    "category_id": category.pk,
                    "title": "برنامه نویس فول استک نیاز دارم",
                    "description": "برای پروژه خیریه نیاز به برنامه نویس فول استک دارم",
                },
                format="json",
            )

        assert create_response.status_code == status.HTTP_201_CREATED
        listing_id = create_response.data["data"]["id"]
        assert mock_task.delay.call_args.kwargs["action"] == audit_actions.KINDNESS_LISTING_CREATED

        update_response = client.patch(
            reverse("kindness_wall:user-listing-detail", kwargs={"listing_id": listing_id}),
            data={"title": "برنامه نویس Django نیاز دارم"},
            format="json",
        )
        assert update_response.status_code == status.HTTP_200_OK

        submit_response = client.post(
            reverse("kindness_wall:user-listing-submit", kwargs={"listing_id": listing_id})
        )
        assert submit_response.status_code == status.HTTP_200_OK
        assert submit_response.data["data"]["status"] == ListingStatus.PENDING_REVIEW

    def test_user_cannot_access_other_user_listing(self) -> None:
        listing = _make_pending_listing()
        other = KindnessUserFactory()

        response = _client_for(other).get(
            reverse("kindness_wall:user-listing-detail", kwargs={"listing_id": listing.pk})
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestKindnessBookmarkReportAndMatchesAPI:
    """Bookmark/report/match API behavior."""

    def test_bookmark_create_and_delete(self) -> None:
        listing = PublishedOfferListingFactory()
        user = KindnessUserFactory()
        client = _client_for(user)

        create_response = client.post(
            reverse("kindness_wall:listing-bookmark", kwargs={"slug": listing.slug})
        )
        delete_response = client.delete(
            reverse("kindness_wall:listing-bookmark", kwargs={"slug": listing.slug})
        )

        assert create_response.status_code == status.HTTP_201_CREATED
        assert delete_response.status_code == status.HTTP_200_OK
        assert KindnessBookmark.objects.count() == 0

    def test_report_listing(self) -> None:
        listing = PublishedNeedListingFactory()
        user = KindnessUserFactory()

        response = _client_for(user).post(
            reverse("kindness_wall:listing-report", kwargs={"slug": listing.slug}),
            data={"reason": ReportReason.SPAM, "description": "آگهی اسپم است"},
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert KindnessListingReport.objects.filter(listing=listing, reported_by=user).exists()

    def test_user_can_list_and_dismiss_own_match(self) -> None:
        source = PublishedNeedListingFactory()
        target = PublishedOfferListingFactory(category=source.category)
        match = KindnessMatch.objects.create(source_listing=source, target_listing=target, score=80)
        client = _client_for(source.owner)

        list_response = client.get(reverse("kindness_wall:user-match-list"))
        dismiss_response = client.post(
            reverse("kindness_wall:user-match-dismiss", kwargs={"match_id": match.pk})
        )

        assert list_response.status_code == status.HTTP_200_OK
        assert list_response.data["data"]["count"] == 1
        assert dismiss_response.status_code == status.HTTP_200_OK
        match.refresh_from_db()
        assert match.status == "dismissed"


class TestKindnessAdminAPI:
    """Admin moderation endpoints."""

    def test_admin_can_approve_reject_suspend_restore_and_review_report(self) -> None:
        admin = AdminUserFactory()
        client = _client_for(admin)
        pending = _make_pending_listing()

        approve_response = client.post(
            reverse("kindness_wall:admin-listing-approve", kwargs={"listing_id": pending.pk})
        )
        assert approve_response.status_code == status.HTTP_200_OK
        pending.refresh_from_db()
        assert pending.status == ListingStatus.PUBLISHED

        suspend_response = client.post(
            reverse("kindness_wall:admin-listing-suspend", kwargs={"listing_id": pending.pk}),
            data={"reason": "گزارش تخلف"},
            format="json",
        )
        assert suspend_response.status_code == status.HTTP_200_OK
        pending.refresh_from_db()
        assert pending.status == ListingStatus.SUSPENDED

        restore_response = client.post(
            reverse("kindness_wall:admin-listing-restore", kwargs={"listing_id": pending.pk})
        )
        assert restore_response.status_code == status.HTTP_200_OK

        report = KindnessListingReport.objects.create(
            listing=pending, reported_by=KindnessUserFactory(), reason=ReportReason.OTHER
        )
        review_response = client.post(
            reverse("kindness_wall:admin-report-review", kwargs={"report_id": report.pk}),
            data={"reason": ReportStatus.REVIEWED, "admin_note": "بررسی شد"},
            format="json",
        )
        assert review_response.status_code == status.HTTP_200_OK
        report.refresh_from_db()
        assert report.status == ReportStatus.REVIEWED

    def test_regular_user_cannot_access_admin_listing_list(self) -> None:
        user = KindnessUserFactory()

        response = _client_for(user).get(reverse("kindness_wall:admin-listing-list"))

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_analytics_endpoint(self) -> None:
        PublishedNeedListingFactory()
        response = _client_for(AdminUserFactory()).get(reverse("kindness_wall:admin-analytics"))

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["total_listings"] >= 1
