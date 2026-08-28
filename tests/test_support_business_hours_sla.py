"""Support Apex C1 business-hours SLA calendar tests."""

from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.support_desk.choices import TicketPriority, TicketSeverity
from apps.support_desk.models import SupportBusinessCalendar, SupportHoliday
from apps.support_desk.services import add_business_minutes, create_ticket, submit_ticket
from tests.factories import AdminUserFactory, UserFactory
from tests.factories.support_desk import (
    SupportCategoryFactory,
    SupportDepartmentFactory,
    SupportSLAPolicyFactory,
    SupportTicketTypeFactory,
)

pytestmark = pytest.mark.django_db


def _client_for(user) -> APIClient:
    """Return authenticated API client."""
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _aware(year: int, month: int, day: int, hour: int, minute: int = 0):
    """Build Tehran-aware datetime."""
    return datetime(year, month, day, hour, minute, tzinfo=ZoneInfo("Asia/Tehran"))


def test_add_business_minutes_rolls_over_to_next_working_day() -> None:
    """SLA minutes should roll over after business hours."""
    department = SupportDepartmentFactory()
    calendar = SupportBusinessCalendar.objects.create(
        title="تقویم کاری تست",
        department=department,
        workday_start=time(9, 0),
        workday_end=time(17, 0),
        active_weekdays=[0, 1],
        is_default=True,
    )

    due = add_business_minutes(start_at=_aware(2026, 6, 15, 16, 30), minutes=60, calendar=calendar)

    assert due == _aware(2026, 6, 16, 9, 30)


def test_business_minutes_skip_holidays() -> None:
    """SLA calculations should skip configured holidays."""
    department = SupportDepartmentFactory()
    calendar = SupportBusinessCalendar.objects.create(
        title="تقویم با تعطیلی",
        department=department,
        workday_start=time(9, 0),
        workday_end=time(17, 0),
        active_weekdays=[0, 1, 2],
    )
    SupportHoliday.objects.create(calendar=calendar, date=date(2026, 6, 16), title="تعطیلی تست")

    due = add_business_minutes(start_at=_aware(2026, 6, 15, 16, 30), minutes=60, calendar=calendar)

    assert due == _aware(2026, 6, 17, 9, 30)


def test_submit_ticket_uses_business_hours_sla_policy() -> None:
    """Submitting a ticket with business-hours SLA should use the calendar."""
    department = SupportDepartmentFactory(title="SLA تقویمی")
    category = SupportCategoryFactory(department=department)
    SupportBusinessCalendar.objects.create(
        title="تقویم SLA",
        department=department,
        workday_start=time(9, 0),
        workday_end=time(17, 0),
        active_weekdays=[0, 1],
        is_default=True,
    )
    policy = SupportSLAPolicyFactory(
        title="SLA ساعت کاری",
        department=department,
        priority=TicketPriority.HIGH,
        severity=TicketSeverity.MAJOR,
        first_response_minutes=60,
        resolution_minutes=120,
        business_hours_only=True,
    )
    ticket_type = SupportTicketTypeFactory(
        default_department=department,
        default_category=category,
        default_sla_policy=policy,
        default_priority=TicketPriority.HIGH,
        default_severity=TicketSeverity.MAJOR,
    )
    ticket = create_ticket(
        owner=UserFactory(),
        ticket_type=ticket_type,
        subject="ساعت کاری",
        description="محاسبه SLA ساعت کاری",
    )

    submit_ticket(ticket=ticket, user=ticket.owner, now=_aware(2026, 6, 15, 16, 30))
    ticket.refresh_from_db()

    assert ticket.first_response_due_at == _aware(2026, 6, 16, 9, 30)
    assert ticket.resolution_due_at == _aware(2026, 6, 16, 10, 30)


def test_admin_can_manage_business_calendars_and_holidays() -> None:
    """Admin APIs should manage calendars and holidays through service layer."""
    department = SupportDepartmentFactory(title="تقویم API")
    client = _client_for(AdminUserFactory())

    create_response = client.post(
        reverse("support_desk:admin-business-calendar-list-create"),
        data={
            "title": "تقویم API",
            "department_id": department.pk,
            "workday_start": "08:30:00",
            "workday_end": "16:30:00",
            "active_weekdays": [0, 1, 2, 3],
            "is_default": True,
        },
        format="json",
    )
    assert create_response.status_code == status.HTTP_201_CREATED
    calendar_id = create_response.data["data"]["id"]

    patch_response = client.patch(
        reverse("support_desk:admin-business-calendar-detail", kwargs={"calendar_id": calendar_id}),
        data={"title": "تقویم API اصلاح‌شده"},
        format="json",
    )
    assert patch_response.status_code == status.HTTP_200_OK
    assert patch_response.data["data"]["title"] == "تقویم API اصلاح‌شده"

    holiday_response = client.post(
        reverse("support_desk:admin-holiday-list-create"),
        data={"calendar_id": calendar_id, "date": "2026-06-16", "title": "تعطیلی API"},
        format="json",
    )
    assert holiday_response.status_code == status.HTTP_201_CREATED
    assert SupportHoliday.objects.filter(calendar_id=calendar_id, date="2026-06-16").exists()
