"""Factories for Support Desk tests."""

from __future__ import annotations

import factory
from factory.django import DjangoModelFactory

from apps.support_desk.choices import TicketPriority, TicketSeverity, TicketStatus
from apps.support_desk.models import (
    SupportCategory,
    SupportDepartment,
    SupportSLAPolicy,
    SupportTicket,
    SupportTicketMessage,
    SupportTicketType,
)
from tests.factories.auth import UserFactory


class SupportDepartmentFactory(DjangoModelFactory):
    """Factory for support departments."""

    class Meta:
        model = SupportDepartment

    title = factory.Sequence(lambda n: f"دپارتمان پشتیبانی {n}")
    description = "توضیحات دپارتمان"
    order = factory.Sequence(lambda n: n)


class SupportCategoryFactory(DjangoModelFactory):
    """Factory for tree support categories."""

    class Meta:
        model = SupportCategory

    department = factory.SubFactory(SupportDepartmentFactory)
    title = factory.Sequence(lambda n: f"دسته پشتیبانی {n}")
    description = "توضیحات دسته"
    order = factory.Sequence(lambda n: n)


class SupportSLAPolicyFactory(DjangoModelFactory):
    """Factory for support SLA policies."""

    class Meta:
        model = SupportSLAPolicy

    title = factory.Sequence(lambda n: f"SLA تست {n}")
    priority = TicketPriority.NORMAL
    severity = TicketSeverity.MINOR
    first_response_minutes = 60
    resolution_minutes = 24 * 60


class SupportTicketTypeFactory(DjangoModelFactory):
    """Factory for dynamic support ticket types."""

    class Meta:
        model = SupportTicketType

    code = factory.Sequence(lambda n: f"type-{n}")
    title = factory.Sequence(lambda n: f"نوع تیکت {n}")
    default_department = factory.SubFactory(SupportDepartmentFactory)
    default_category = factory.SubFactory(
        SupportCategoryFactory, department=factory.SelfAttribute("..default_department")
    )
    default_sla_policy = factory.SubFactory(SupportSLAPolicyFactory)
    default_priority = TicketPriority.NORMAL
    default_severity = TicketSeverity.MINOR


class SupportTicketFactory(DjangoModelFactory):
    """Factory for support tickets."""

    class Meta:
        model = SupportTicket

    owner = factory.SubFactory(UserFactory)
    department = factory.SubFactory(SupportDepartmentFactory)
    category = factory.SubFactory(
        SupportCategoryFactory, department=factory.SelfAttribute("..department")
    )
    ticket_type = factory.SubFactory(
        SupportTicketTypeFactory,
        default_department=factory.SelfAttribute("..department"),
        default_category=factory.SelfAttribute("..category"),
    )
    subject = factory.Sequence(lambda n: f"موضوع تیکت پشتیبانی {n}")
    description_snapshot = "توضیحات کامل تیکت برای بررسی تیم پشتیبانی"
    status = TicketStatus.DRAFT
    priority = TicketPriority.NORMAL
    severity = TicketSeverity.MINOR


class SupportTicketMessageFactory(DjangoModelFactory):
    """Factory for support ticket messages."""

    class Meta:
        model = SupportTicketMessage

    ticket = factory.SubFactory(SupportTicketFactory)
    author = factory.SelfAttribute("ticket.owner")
    message_type = "user_message"
    body = "متن پیام تستی برای تیکت"
    is_internal = False
    is_from_staff = False
