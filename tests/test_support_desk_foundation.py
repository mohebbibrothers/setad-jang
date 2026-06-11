"""Support Desk Phase 1 domain foundation tests."""

from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from apps.support_desk.choices import TicketPriority, TicketSeverity, TicketStatus
from apps.support_desk.models import (
    SupportCannedResponse,
    SupportCategory,
    SupportDepartment,
    SupportSLAPolicy,
    SupportTicketSatisfaction,
    SupportTicketType,
)
from apps.support_desk.validators import validate_duplicate_score
from tests.factories import UserFactory
from tests.factories.support_desk import (
    SupportCategoryFactory,
    SupportDepartmentFactory,
    SupportSLAPolicyFactory,
    SupportTicketFactory,
    SupportTicketTypeFactory,
)

pytestmark = pytest.mark.django_db


class TestSupportDeskSeedTaxonomy:
    """Seed taxonomy must be rich, dynamic and admin-editable."""

    def test_default_departments_categories_ticket_types_sla_and_macros_are_seeded(self) -> None:
        assert SupportDepartment.objects.filter(title="مالی و پرداخت").exists()
        assert SupportDepartment.objects.filter(title="دیوار مهربانی").exists()
        assert SupportCategory.objects.filter(title="پرداخت ناموفق", parent__title="پرداخت و مالی").exists()
        assert SupportCategory.objects.filter(title="مچینگ و پیشنهادها", parent__title="دیوار مهربانی").exists()
        assert SupportTicketType.objects.filter(code="security", title="امنیت و حریم خصوصی").exists()
        assert SupportSLAPolicy.objects.filter(title="فوری / بحرانی", first_response_minutes=120).exists()
        assert SupportCannedResponse.objects.filter(title="پیگیری پرداخت").exists()

    def test_seeded_taxonomy_is_not_hard_locked_and_can_be_edited_by_admin_logic(self) -> None:
        department = SupportDepartment.objects.get(title="پشتیبانی عمومی")
        department.title = "پشتیبانی عمومی و راهنمایی"
        department.save(update_fields=["title", "updated_at"])

        department.refresh_from_db()
        assert department.title == "پشتیبانی عمومی و راهنمایی"


class TestSupportDeskTreeCategories:
    """Tree category invariants for professional support taxonomy."""

    def test_category_generates_slug_path_and_depth(self) -> None:
        department = SupportDepartmentFactory(title="فنی ویژه")
        root = SupportCategoryFactory(department=department, title="مشکلات فنی خاص")
        child = SupportCategoryFactory(department=department, parent=root, title="خطای پنل کاربری")

        assert root.depth == 0
        assert root.path == f"/{root.slug}/"
        assert child.depth == 1
        assert child.path == f"{root.path.rstrip('/')}/{child.slug}/"

    def test_same_title_allowed_under_different_departments_but_not_same_parent_department(self) -> None:
        left_department = SupportDepartmentFactory(title="دپارتمان چپ")
        right_department = SupportDepartmentFactory(title="دپارتمان راست")
        SupportCategoryFactory(department=left_department, title="پیگیری")
        SupportCategoryFactory(department=right_department, title="پیگیری")

        with pytest.raises(IntegrityError):
            SupportCategory.objects.create(department=left_department, title="پیگیری")


class TestSupportDeskTicketFoundation:
    """Ticket core model behavior and constraints."""

    def test_ticket_number_search_document_and_reopen_policy_are_generated(self) -> None:
        ticket = SupportTicketFactory(subject="مشکل پرداخت کمپین", description_snapshot="پرداخت انجام شد اما ثبت نشد")

        assert ticket.ticket_number.startswith("SUP-")
        assert "مشکل پرداخت کمپین" in ticket.search_document
        assert ticket.is_reopenable is False

    def test_ticket_type_is_dynamic_and_carries_routing_defaults(self) -> None:
        department = SupportDepartmentFactory(title="مالی تست")
        category = SupportCategoryFactory(department=department, title="رسید پرداخت تست")
        sla = SupportSLAPolicyFactory(title="SLA مالی تست", priority=TicketPriority.HIGH, severity=TicketSeverity.MAJOR)
        ticket_type = SupportTicketTypeFactory(
            code="payment-test",
            title="پرداخت تست",
            default_department=department,
            default_category=category,
            default_sla_policy=sla,
            default_priority=TicketPriority.HIGH,
            default_severity=TicketSeverity.MAJOR,
        )

        assert ticket_type.default_department == department
        assert ticket_type.default_category == category
        assert ticket_type.default_sla_policy == sla
        assert ticket_type.default_priority == TicketPriority.HIGH

    def test_satisfaction_rating_is_limited_to_one_to_five(self) -> None:
        ticket = SupportTicketFactory(status=TicketStatus.RESOLVED)
        user = ticket.owner

        SupportTicketSatisfaction.objects.create(ticket=ticket, user=user, rating=5)

        with pytest.raises(IntegrityError):
            SupportTicketSatisfaction.objects.create(ticket=SupportTicketFactory(), user=UserFactory(), rating=9)

    def test_duplicate_score_validator_rejects_invalid_scores(self) -> None:
        validate_duplicate_score(0)
        validate_duplicate_score(100)

        with pytest.raises(ValidationError):
            validate_duplicate_score(101)

