"""Managers and querysets for Kindness Wall."""

from django.db import models
from django.utils import timezone

from apps.kindness_wall.choices import ListingStatus


class KindnessCategoryQuerySet(models.QuerySet):
    """QuerySet helpers for tree categories."""

    def active(self):
        """Return active categories."""
        return self.filter(is_active=True)

    def roots(self):
        """Return root categories."""
        return self.filter(parent__isnull=True)


class KindnessCategoryManager(models.Manager.from_queryset(KindnessCategoryQuerySet)):
    """Default active manager for categories."""

    def get_queryset(self):
        """Return active category queryset."""
        return super().get_queryset().filter(is_active=True)


class KindnessCategoryAllManager(models.Manager.from_queryset(KindnessCategoryQuerySet)):
    """Manager exposing all categories."""


class KindnessListingQuerySet(models.QuerySet):
    """QuerySet helpers for listings."""

    def published(self):
        """Return public listings."""
        now = timezone.now()
        return self.filter(
            is_active=True,
            status=ListingStatus.PUBLISHED,
        ).filter(models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=now))

    def opposite_type(self, listing_type: str):
        """Return listings with the opposite fixed type."""
        from apps.kindness_wall.choices import ListingType

        opposite = ListingType.OFFER_HELP if listing_type == ListingType.NEED_HELP else ListingType.NEED_HELP
        return self.filter(listing_type=opposite)


class KindnessListingManager(models.Manager.from_queryset(KindnessListingQuerySet)):
    """Default active listing manager."""

    def get_queryset(self):
        """Return active listings."""
        return super().get_queryset().filter(is_active=True)


class KindnessListingAllManager(models.Manager.from_queryset(KindnessListingQuerySet)):
    """Manager exposing all listings."""
