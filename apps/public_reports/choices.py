from django.db import models


class ReportStatus(models.TextChoices):
    PENDING = "pending", "در انتظار بررسی"
    REVIEWING = "reviewing", "در حال بررسی"
    APPROVED = "approved", "تأیید شده"
    REJECTED = "rejected", "رد شده"
