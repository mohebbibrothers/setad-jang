"""
Reusable active/all-objects querysets and managers for soft-delete models.
"""

from django.db import models


class BaseQuerySet(models.QuerySet):
    """BaseQuerySet implementation for the core application."""
    def active(self):
        return self.filter(is_active=True)

    def inactive(self):
        return self.filter(is_active=False)

    def soft_delete(self):
        return self.update(is_active=False)

    def restore(self):
        return self.update(is_active=True)


class ActiveManager(models.Manager):
    """ActiveManager implementation for the core application."""
    def get_queryset(self):
        return BaseQuerySet(self.model, using=self._db).filter(is_active=True)


class AllObjectsManager(models.Manager):
    """AllObjectsManager implementation for the core application."""
    def get_queryset(self):
        return BaseQuerySet(self.model, using=self._db)
