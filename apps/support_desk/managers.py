"""Managers and querysets for Support Desk."""

from django.db import models

from apps.support_desk.choices import TicketStatus


class SupportCategoryQuerySet(models.QuerySet):
    """QuerySet helpers for support category tree."""

    def active(self):
        """Return active categories."""
        return self.filter(is_active=True)

    def roots(self):
        """Return root categories."""
        return self.filter(parent__isnull=True)


class SupportTicketQuerySet(models.QuerySet):
    """QuerySet helpers for support tickets."""

    def open_queue(self):
        """Return tickets that still need operational attention."""
        return self.exclude(status__in={TicketStatus.CLOSED, TicketStatus.ARCHIVED, TicketStatus.SPAM})

    def overdue(self):
        """Return tickets with breached SLA markers."""
        return self.filter(sla_breached_at__isnull=False)

    def assigned_to(self, user):
        """Return tickets assigned to a specific admin user."""
        return self.filter(assigned_to=user)


class SupportCategoryManager(models.Manager.from_queryset(SupportCategoryQuerySet)):
    """Default active category manager."""

    def get_queryset(self):
        """Return only active categories by default."""
        return super().get_queryset().filter(is_active=True)


class SupportCategoryAllManager(models.Manager.from_queryset(SupportCategoryQuerySet)):
    """Manager exposing all categories including inactive ones."""


class SupportTicketManager(models.Manager.from_queryset(SupportTicketQuerySet)):
    """Default active ticket manager."""

    def get_queryset(self):
        """Return only active tickets by default."""
        return super().get_queryset().filter(is_active=True)


class SupportTicketAllManager(models.Manager.from_queryset(SupportTicketQuerySet)):
    """Manager exposing all tickets including inactive ones."""
