"""Support Desk Phase 2 service workflow, SLA, and smart triage tests."""

from __future__ import annotations

import pytest
from django.utils import timezone

from apps.support_desk.choices import (
    DuplicateReviewStatus,
    SLAEventType,
    TicketMessageType,
    TicketPriority,
    TicketSeverity,
    TicketStatus,
)
from apps.support_desk.models import (
    SupportSLAEvent,
    SupportTag,
    SupportTicketAssignment,
    SupportTicketMessage,
    SupportTicketStatusHistory,
)
from apps.support_desk.services import (
    SupportPermissionError,
    SupportTaxonomyTreeError,
    SupportTicketStateError,
    add_admin_reply,
    add_internal_note,
    add_user_reply,
    assign_ticket,
    change_ticket_status,
    close_ticket,
    create_category,
    create_ticket,
    deactivate_category,
    detect_duplicate_candidates,
    escalate_ticket,
    mark_sla_breaches,
    reopen_ticket,
    resolve_ticket,
    review_duplicate_candidate,
    submit_satisfaction,
    submit_ticket,
    suggest_ticket_triage,
    update_category,
)
from tests.factories import AdminUserFactory, UserFactory
from tests.factories.support_desk import (
    SupportCategoryFactory,
    SupportDepartmentFactory,
    SupportSLAPolicyFactory,
    SupportTicketFactory,
    SupportTicketTypeFactory,
)

pytestmark = pytest.mark.django_db


def _make_type_with_policy(*, first_minutes: int = 60, resolution_minutes: int = 24 * 60):
    """Create a routed ticket type with SLA policy."""
    department = SupportDepartmentFactory(title="پشتیبانی سرویس")
    category = SupportCategoryFactory(department=department, title="دسته سرویس")
    policy = SupportSLAPolicyFactory(
        title="SLA سرویس",
        department=department,
        priority=TicketPriority.HIGH,
        severity=TicketSeverity.MAJOR,
        first_response_minutes=first_minutes,
        resolution_minutes=resolution_minutes,
    )
    ticket_type = SupportTicketTypeFactory(
        code="service-flow",
        title="جریان سرویس",
        default_department=department,
        default_category=category,
        default_sla_policy=policy,
        default_priority=TicketPriority.HIGH,
        default_severity=TicketSeverity.MAJOR,
    )
    return ticket_type, department, category, policy


class TestSupportTicketCreationAndSubmit:
    """Ticket creation and submit SLA workflow."""

    def test_create_ticket_uses_dynamic_defaults_and_creates_timeline_tags_duplicates(self) -> None:
        ticket_type, department, category, _policy = _make_type_with_policy()
        owner = UserFactory()

        ticket = create_ticket(
            owner=owner,
            ticket_type=ticket_type,
            subject="مشکل پرداخت کمپین مددکار",
            description="پرداخت انجام شد اما در کمپین ثبت نشده است",
        )

        assert ticket.status == TicketStatus.DRAFT
        assert ticket.department == department
        assert ticket.category == category
        assert ticket.priority == TicketPriority.HIGH
        assert ticket.severity == TicketSeverity.MAJOR
        assert ticket.assigned_to is None
        assert (
            ticket.messages.filter(
                message_type=TicketMessageType.USER_MESSAGE, is_internal=False
            ).count()
            == 1
        )
        assert ticket.message_count >= 1
        assert SupportTicketStatusHistory.objects.filter(
            ticket=ticket, to_status=TicketStatus.DRAFT
        ).exists()
        assert SupportTag.objects.filter(ticket_tags__ticket=ticket).exists()

    def test_submit_ticket_applies_sla_and_changes_status(self) -> None:
        ticket_type, _department, _category, policy = _make_type_with_policy(
            first_minutes=30, resolution_minutes=90
        )
        owner = UserFactory()
        now = timezone.now()
        ticket = create_ticket(
            owner=owner, ticket_type=ticket_type, subject="مشکل فنی", description="صفحه خطا می‌دهد"
        )

        submitted = submit_ticket(ticket=ticket, user=owner, now=now)

        assert submitted.status == TicketStatus.SUBMITTED
        assert submitted.submitted_at == now
        assert submitted.applied_sla_policy == policy
        assert submitted.first_response_due_at == now + timezone.timedelta(minutes=30)
        assert submitted.resolution_due_at == now + timezone.timedelta(minutes=90)
        assert SupportSLAEvent.objects.filter(
            ticket=ticket, event_type=SLAEventType.POLICY_APPLIED
        ).exists()

    def test_non_owner_cannot_submit_ticket(self) -> None:
        ticket = SupportTicketFactory()

        with pytest.raises(SupportPermissionError):
            submit_ticket(ticket=ticket, user=UserFactory())


class TestSupportConversationWorkflow:
    """User/admin conversation and state transitions."""

    def test_admin_reply_sets_first_response_waiting_for_user_and_pauses_sla(self) -> None:
        ticket_type, _department, _category, _policy = _make_type_with_policy(
            first_minutes=30, resolution_minutes=90
        )
        owner = UserFactory()
        admin = AdminUserFactory()
        now = timezone.now()
        ticket = submit_ticket(
            ticket=create_ticket(
                owner=owner, ticket_type=ticket_type, subject="پرداخت", description="رسید ثبت نشده"
            ),
            user=owner,
            now=now,
        )

        message = add_admin_reply(
            ticket=ticket,
            admin=admin,
            body="لطفاً شماره پیگیری را ارسال کنید",
            now=now + timezone.timedelta(minutes=10),
        )
        ticket.refresh_from_db()

        assert message.message_type == TicketMessageType.ADMIN_REPLY
        assert ticket.status == TicketStatus.WAITING_FOR_USER
        assert ticket.first_admin_response_at == now + timezone.timedelta(minutes=10)
        assert ticket.sla_paused_at == now + timezone.timedelta(minutes=10)
        assert SupportSLAEvent.objects.filter(
            ticket=ticket, event_type=SLAEventType.PAUSED
        ).exists()

    def test_user_reply_resumes_sla_and_moves_to_waiting_for_admin(self) -> None:
        ticket_type, _department, _category, _policy = _make_type_with_policy(
            first_minutes=30, resolution_minutes=90
        )
        owner = UserFactory()
        admin = AdminUserFactory()
        now = timezone.now()
        ticket = submit_ticket(
            ticket=create_ticket(
                owner=owner, ticket_type=ticket_type, subject="پرداخت", description="رسید ثبت نشده"
            ),
            user=owner,
            now=now,
        )
        add_admin_reply(
            ticket=ticket,
            admin=admin,
            body="شماره پیگیری؟",
            now=now + timezone.timedelta(minutes=5),
        )
        ticket.refresh_from_db()
        original_resolution_due = ticket.resolution_due_at

        add_user_reply(
            ticket=ticket,
            user=owner,
            body="شماره پیگیری ۱۲۳۴",
            now=now + timezone.timedelta(minutes=65),
        )
        ticket.refresh_from_db()

        assert ticket.status == TicketStatus.WAITING_FOR_ADMIN
        assert ticket.sla_paused_at is None
        assert ticket.sla_total_paused_seconds == 60 * 60
        assert ticket.resolution_due_at == original_resolution_due + timezone.timedelta(hours=1)
        assert SupportSLAEvent.objects.filter(
            ticket=ticket, event_type=SLAEventType.RESUMED
        ).exists()

    def test_internal_note_is_admin_only_and_hidden_by_flag(self) -> None:
        ticket = SupportTicketFactory(status=TicketStatus.SUBMITTED)
        admin = AdminUserFactory()

        note = add_internal_note(ticket=ticket, admin=admin, body="برای تیم مالی بررسی شود")

        assert note.is_internal is True
        assert note.message_type == TicketMessageType.INTERNAL_NOTE
        ticket.refresh_from_db()
        assert ticket.internal_note_count == 1

        with pytest.raises(SupportPermissionError):
            add_internal_note(ticket=ticket, admin=UserFactory(), body="نباید مجاز باشد")

    def test_assignment_records_history_and_internal_timeline(self) -> None:
        ticket = SupportTicketFactory(status=TicketStatus.SUBMITTED)
        admin = AdminUserFactory()
        assignee = AdminUserFactory(email="assignee-support@test.local")
        department = SupportDepartmentFactory(title="ارجاع ویژه")

        assign_ticket(
            ticket=ticket,
            admin=admin,
            assignee=assignee,
            department=department,
            reason="نیاز به بررسی تخصصی",
        )
        ticket.refresh_from_db()

        assert ticket.assigned_to == assignee
        assert ticket.department == department
        assert SupportTicketAssignment.objects.filter(ticket=ticket, assigned_to=assignee).exists()
        assert SupportTicketMessage.objects.filter(
            ticket=ticket, message_type=TicketMessageType.ASSIGNMENT_CHANGE, is_internal=True
        ).exists()


class TestSupportStatusResolutionAndSatisfaction:
    """Resolution, close, reopen and satisfaction services."""

    def test_resolve_close_reopen_and_satisfaction_flow(self) -> None:
        ticket = SupportTicketFactory(status=TicketStatus.SUBMITTED)
        admin = AdminUserFactory()

        resolve_ticket(ticket=ticket, admin=admin, reason="مشکل حل شد")
        ticket.refresh_from_db()
        assert ticket.status == TicketStatus.RESOLVED
        assert ticket.resolved_at is not None

        satisfaction = submit_satisfaction(
            ticket=ticket, user=ticket.owner, rating=5, comment="عالی"
        )
        ticket.refresh_from_db()
        assert satisfaction.rating == 5
        assert ticket.satisfaction_rating_snapshot == 5

        close_ticket(ticket=ticket, actor=ticket.owner, reason="تأیید کاربر")
        ticket.refresh_from_db()
        assert ticket.status == TicketStatus.CLOSED
        assert ticket.closed_at is not None
        assert ticket.is_reopenable is True

        reopen_ticket(ticket=ticket, user=ticket.owner, reason="مشکل برگشت")
        ticket.refresh_from_db()
        assert ticket.status == TicketStatus.REOPENED
        assert ticket.reopen_count == 1

    def test_invalid_status_and_non_admin_status_change_are_rejected(self) -> None:
        ticket = SupportTicketFactory(status=TicketStatus.SUBMITTED)

        with pytest.raises(SupportPermissionError):
            change_ticket_status(
                ticket=ticket, admin=UserFactory(), status=TicketStatus.IN_PROGRESS
            )
        with pytest.raises(SupportTicketStateError):
            change_ticket_status(ticket=ticket, admin=AdminUserFactory(), status="unknown")


class TestSupportSLAAndEscalation:
    """SLA breach and escalation services."""

    def test_mark_sla_breaches_marks_and_escalates_ticket(self) -> None:
        ticket_type, _department, _category, _policy = _make_type_with_policy(
            first_minutes=1, resolution_minutes=2
        )
        owner = UserFactory()
        now = timezone.now()
        ticket = submit_ticket(
            ticket=create_ticket(
                owner=owner, ticket_type=ticket_type, subject="بحرانی", description="خطای مهم"
            ),
            user=owner,
            now=now,
        )

        updated = mark_sla_breaches(now=now + timezone.timedelta(minutes=3))
        ticket.refresh_from_db()

        assert updated == 1
        assert ticket.sla_breached_at is not None
        assert ticket.status == TicketStatus.ESCALATED
        assert SupportSLAEvent.objects.filter(
            ticket=ticket, event_type=SLAEventType.ESCALATED
        ).exists()

    def test_manual_escalation_requires_admin(self) -> None:
        ticket = SupportTicketFactory(status=TicketStatus.SUBMITTED)

        with pytest.raises(SupportPermissionError):
            escalate_ticket(ticket=ticket, admin=UserFactory(), reason="فوری")

        escalated = escalate_ticket(ticket=ticket, admin=AdminUserFactory(), reason="فوری")
        assert escalated.status == TicketStatus.ESCALATED


class TestSupportSmartTriageAndDuplicates:
    """Smart triage and duplicate candidate services.

    `suggest_ticket_triage` به انواع تیکتِ seedشده (مثل code="payment")
    وابسته است؛ چون تست‌های تراکنشی کل دیتابیس را flush می‌کنند (روی
    PostgreSQL یعنی TRUNCATE)، seed در این fixture idempotent بازسازی
    می‌شود تا ترتیب اجرا اثری نداشته باشد.
    """

    @pytest.fixture(autouse=True)
    def _ensure_seeds(self, db):
        from tests.seed_helpers import reseed_support_taxonomy

        reseed_support_taxonomy()

    def test_smart_triage_suggests_payment_priority_and_similar_tickets(self) -> None:
        owner = UserFactory()
        from apps.support_desk.models import SupportTicketType

        payment_type = SupportTicketType.objects.get(code="payment")
        existing = create_ticket(
            owner=owner,
            ticket_type=payment_type,
            subject="پرداخت ثبت نشده",
            description="پرداخت انجام شده اما ثبت نشده",
        )

        suggestion = suggest_ticket_triage(
            owner=owner, subject="پرداخت ثبت نشده", description="پرداخت انجام شده اما ثبت نشده"
        )

        assert suggestion.priority == TicketPriority.HIGH
        assert suggestion.severity == TicketSeverity.MAJOR
        assert suggestion.duplicate_warning is True
        assert existing.pk in suggestion.similar_ticket_ids
        assert "payment_keyword_priority_boost" in suggestion.reason_codes

    def test_duplicate_detection_and_review(self) -> None:
        owner = UserFactory()
        ticket_type, _department, _category, _policy = _make_type_with_policy()
        first = create_ticket(
            owner=owner,
            ticket_type=ticket_type,
            subject="پرداخت ثبت نشده",
            description="پرداخت انجام شده اما ثبت نشده",
        )
        second = create_ticket(
            owner=owner,
            ticket_type=ticket_type,
            subject="پرداخت ثبت نشده",
            description="پرداخت انجام شده اما ثبت نشده",
        )

        duplicates = detect_duplicate_candidates(ticket=second, threshold=50)
        duplicate = duplicates[0]

        assert duplicate.candidate_ticket == first
        reviewed = review_duplicate_candidate(
            duplicate=duplicate,
            admin=AdminUserFactory(),
            status=DuplicateReviewStatus.CONFIRMED,
            reason="تکراری است",
        )
        assert reviewed.status == DuplicateReviewStatus.CONFIRMED
        assert reviewed.reviewed_at is not None


class TestSupportTaxonomyServices:
    """Taxonomy service invariants."""

    def test_category_create_move_cycle_and_deactivate_guards(self) -> None:
        department = SupportDepartmentFactory(title="درخت سرویس")
        root = create_category(department=department, title="ریشه")
        child = create_category(department=department, parent=root, title="فرزند")

        with pytest.raises(SupportTaxonomyTreeError):
            update_category(category=root, parent=child)

        ticket_type = SupportTicketTypeFactory(
            default_department=department, default_category=child
        )
        ticket = create_ticket(
            owner=UserFactory(), ticket_type=ticket_type, subject="باز", description="تیکت باز"
        )
        submit_ticket(ticket=ticket, user=ticket.owner)

        with pytest.raises(SupportTaxonomyTreeError):
            deactivate_category(category=child)
