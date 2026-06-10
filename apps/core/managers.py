from django.db import models


class BaseQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)

    def inactive(self):
        return self.filter(is_active=False)

    def soft_delete(self):
        return self.update(is_active=False)

    def restore(self):
        return self.update(is_active=True)


class ActiveManager(models.Manager):
    def get_queryset(self):
        return BaseQuerySet(self.model, using=self._db).filter(is_active=True)


class AllObjectsManager(models.Manager):
    def get_queryset(self):
        return BaseQuerySet(self.model, using=self._db)
