"""
Test Factories — central registry.

تمام factoryهای پروژه از اینجا re-export می‌شوند تا import در تست‌ها
تمیز، یکپارچه و discoverable باشد.

اصول طراحی:
- تمام factoryهای قابل استفاده در تست‌ها باید از این registry در دسترس باشند.
- importها alphabetical مرتب شده‌اند — هم per-module و هم per-name.
- هر اپ جدید که factory دارد باید اینجا register شود.
- تست‌ها تا حد ممکن از این فایل import می‌کنند، نه مستقیم از submoduleها.

Usage:
    from tests.factories import UserFactory, R4JCriminalFactory
"""

# ── Audit Logs ──────────────────────────────────────────────
from .audit_logs import AuditLogFactory

# ── Authentication ──────────────────────────────────────────
from .auth import AdminUserFactory, UserFactory

# ── LMS (Learning Management System) ────────────────────────
from .lms import (
    CertificateFactory,
    CourseFactory,
    EnrollmentFactory,
    LessonFactory,
    LessonProgressFactory,
    LMSCategoryFactory,
    LMSUserSkillFactory,
    PublishedCourseFactory,
    PublishedQuizFactory,
    QuizAttemptFactory,
    QuizFactory,
    QuizOptionFactory,
    QuizQuestionFactory,
)

# ── Madadkar (Charitable Crowdfunding) ──────────────────────
from .madadkar import (
    CampaignFactory,
    CampaignImageFactory,
    CampaignWithDeadlineFactory,
    ClosedCampaignFactory,
    CompletedCampaignFactory,
    ExpiredParticipationFactory,
    FailedParticipationFactory,
    FailedPaymentFactory,
    PaidParticipationFactory,
    ParticipationFactory,
    PaymentFactory,
    PublishedCampaignFactory,
    SponsorFactory,
    SponsorWithLogoFactory,
    SuccessPaymentFactory,
)

# ── Public Reports ──────────────────────────────────────────
from .public_reports import ReportFactory, ReportSubjectFactory

# ── R4J (Reward for Justice) ────────────────────────────────
from .r4j import (
    R4JBountyFactory,
    R4JCriminalFactory,
    R4JCriminalPublishedFactory,
    R4JReportAttachmentFactory,
    R4JReportFactory,
    R4JReportFieldChangeFactory,
)

# ── Tabyin ──────────────────────────────────────────────────
from .tabyin import TabyinAttachmentFactory, TabyinContentFactory

__all__ = [
    "AdminUserFactory",
    "AuditLogFactory",
    "CampaignFactory",
    "CampaignImageFactory",
    "CampaignWithDeadlineFactory",
    "CertificateFactory",
    "ClosedCampaignFactory",
    "CompletedCampaignFactory",
    "CourseFactory",
    "EnrollmentFactory",
    "ExpiredParticipationFactory",
    "FailedParticipationFactory",
    "FailedPaymentFactory",
    "KindnessCategoryFactory",
    "KindnessListingFactory",
    "KindnessTagFactory",
    "KindnessUserFactory",
    "LMSCategoryFactory",
    "LMSUserSkillFactory",
    "LessonFactory",
    "LessonProgressFactory",
    "PaidParticipationFactory",
    "ParticipationFactory",
    "PaymentFactory",
    "PublishedCampaignFactory",
    "PublishedCourseFactory",
    "PublishedNeedListingFactory",
    "PublishedOfferListingFactory",
    "PublishedQuizFactory",
    "QuizAttemptFactory",
    "QuizFactory",
    "QuizOptionFactory",
    "QuizQuestionFactory",
    "R4JBountyFactory",
    "R4JCriminalFactory",
    "R4JCriminalPublishedFactory",
    "R4JReportAttachmentFactory",
    "R4JReportFactory",
    "R4JReportFieldChangeFactory",
    "ReportFactory",
    "ReportSubjectFactory",
    "SponsorFactory",
    "SponsorWithLogoFactory",
    "SuccessPaymentFactory",
    "TabyinAttachmentFactory",
    "TabyinContentFactory",
    "UserFactory",
]
