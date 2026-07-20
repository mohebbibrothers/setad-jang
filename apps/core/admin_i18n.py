"""Centralized Persian labels for Django admin UX.

This module intentionally patches only presentation metadata (AppConfig and
Model._meta verbose names). It does not alter database schema and therefore does
not require migrations. Keeping these labels centralized lets us also localize
third-party admin entries such as SimpleJWT token blacklist and Django auth.
"""

from __future__ import annotations

from django.apps import apps

APP_VERBOSE_NAMES: dict[str, str] = {
    "activity": "خط زمانی فعالیت کاربران",
    "audit_logs": "لاگ فعالیت‌ها",
    "auth": "دسترسی‌ها و گروه‌ها",
    "authentication": "احراز هویت و کاربران",
    "core": "هسته مرکزی",
    "kindness_wall": "دیوار مهربانی",
    "lms": "سامانه آموزش بعثت مردم",
    "madadkar": "مددکار و حرکت‌های مردمی",
    "notifications": "اعلان‌ها و پیام‌ها",
    "public_reports": "گزارش‌های مردمی",
    "r4j": "جایزه‌ای برای عدالت",
    "support_desk": "میز پشتیبانی",
    "tabyin": "جهاد تبیین",
    "token_blacklist": "مدیریت توکن‌ها",
}

# key: (app_label, model_name_lower) -> (verbose_name, verbose_name_plural)
MODEL_VERBOSE_NAMES: dict[tuple[str, str], tuple[str, str]] = {
    # Third-party / Django contrib
    ("auth", "group"): ("گروه دسترسی", "گروه‌های دسترسی"),
    ("token_blacklist", "blacklistedtoken"): (
        "توکن مسدودشده",
        "توکن‌های مسدودشده",
    ),
    ("token_blacklist", "outstandingtoken"): (
        "توکن صادرشده فعال",
        "توکن‌های صادرشده فعال",
    ),

    # Core / platform
    ("core", "cacheinvalidationevent"): (
        "رویداد ابطال کش",
        "رویدادهای ابطال کش و بازاعتبارسنجی",
    ),
    ("activity", "useractivity"): (
        "رویداد فعالیت کاربر",
        "رویدادهای فعالیت کاربران",
    ),
    ("audit_logs", "auditlog"): ("لاگ فعالیت", "لاگ‌های فعالیت"),

    # Authentication
    ("authentication", "user"): ("کاربر", "کاربران"),
    ("authentication", "profile"): ("پروفایل کاربر", "پروفایل‌های کاربران"),
    ("authentication", "otpcode"): ("کد یکبارمصرف", "کدهای یکبارمصرف"),
    ("authentication", "authsession"): (
        "نشست احراز هویت",
        "نشست‌های احراز هویت",
    ),
    ("authentication", "authrisksignal"): (
        "سیگنال ریسک احراز هویت",
        "سیگنال‌های ریسک احراز هویت",
    ),

    # Notifications
    ("notifications", "notificationtemplate"): (
        "قالب اعلان",
        "قالب‌های اعلان",
    ),
    ("notifications", "notificationevent"): (
        "رویداد اعلان",
        "رویدادهای اعلان",
    ),
    ("notifications", "notificationdelivery"): (
        "ارسال اعلان",
        "ارسال‌های اعلان",
    ),
    ("notifications", "notificationpreference"): (
        "ترجیح اعلان کاربر",
        "ترجیحات اعلان کاربران",
    ),

    # R4J
    ("r4j", "r4jcriminal"): ("مجرم", "مجرمان"),
    ("r4j", "r4jcriminalalias"): ("نام مستعار مجرم", "نام‌های مستعار مجرمان"),
    ("r4j", "r4jcriminalphone"): ("شماره تماس مجرم", "شماره‌های تماس مجرمان"),
    ("r4j", "r4jcriminalsocial"): (
        "حساب شبکه اجتماعی مجرم",
        "حساب‌های شبکه اجتماعی مجرمان",
    ),
    ("r4j", "r4jcriminalphoto"): ("عکس مجرم", "عکس‌های مجرمان"),
    ("r4j", "r4jcriminalattachment"): ("سند مجرم", "اسناد مجرمان"),
    ("r4j", "r4jcriminalfieldvisibility"): (
        "تنظیم نمایش فیلد مجرم",
        "تنظیمات نمایش فیلدهای مجرمان",
    ),
    ("r4j", "r4jreport"): ("گزارش عدالت", "گزارش‌های عدالت"),
    ("r4j", "r4jreportfieldchange"): (
        "پیشنهاد اصلاح فیلد گزارش",
        "پیشنهادهای اصلاح فیلدهای گزارش",
    ),
    ("r4j", "r4jreportattachment"): ("ضمیمه گزارش عدالت", "ضمائم گزارش‌های عدالت"),
    ("r4j", "r4jevidencecustodyevent"): (
        "رویداد زنجیره نگهداری شواهد",
        "رویدادهای زنجیره نگهداری شواهد",
    ),
    ("r4j", "r4jinvestigationcase"): (
        "پرونده عملیاتی عدالت",
        "پرونده‌های عملیاتی عدالت",
    ),
    ("r4j", "r4jcaseevent"): ("رویداد پرونده عدالت", "رویدادهای پرونده عدالت"),
    ("r4j", "r4jbounty"): ("جایزه عدالت", "جوایز عدالت"),

    # Tabyin
    ("tabyin", "tabyincontent"): ("محتوای تبیین", "محتواهای تبیین"),
    ("tabyin", "tabyinattachment"): ("پیوست تبیین", "پیوست‌های تبیین"),

    # Kindness wall
    ("kindness_wall", "kindnesscategory"): (
        "دسته‌بندی دیوار مهربانی",
        "دسته‌بندی‌های دیوار مهربانی",
    ),
    ("kindness_wall", "kindnesstag"): ("تگ دیوار مهربانی", "تگ‌های دیوار مهربانی"),
    ("kindness_wall", "kindnesskeywordalias"): (
        "هم‌معنی جستجوی دیوار مهربانی",
        "هم‌معنی‌های جستجوی دیوار مهربانی",
    ),
    ("kindness_wall", "kindnesslisting"): (
        "آگهی دیوار مهربانی",
        "آگهی‌های دیوار مهربانی",
    ),
    ("kindness_wall", "kindnesslistingimage"): (
        "تصویر آگهی دیوار مهربانی",
        "تصاویر آگهی دیوار مهربانی",
    ),
    ("kindness_wall", "kindnesslistingtag"): (
        "تگ آگهی دیوار مهربانی",
        "تگ‌های آگهی دیوار مهربانی",
    ),
    ("kindness_wall", "kindnessmatch"): (
        "تطبیق آگهی دیوار مهربانی",
        "تطبیق‌های آگهی دیوار مهربانی",
    ),
    ("kindness_wall", "kindnesscontactreveal"): (
        "نمایش اطلاعات تماس دیوار مهربانی",
        "نمایش‌های اطلاعات تماس دیوار مهربانی",
    ),
    ("kindness_wall", "kindnesslistingreport"): (
        "گزارش آگهی دیوار مهربانی",
        "گزارش‌های آگهی دیوار مهربانی",
    ),
    ("kindness_wall", "kindnessbookmark"): (
        "نشانک دیوار مهربانی",
        "نشانک‌های دیوار مهربانی",
    ),
    ("kindness_wall", "kindnessrisksignal"): (
        "سیگنال ریسک دیوار مهربانی",
        "سیگنال‌های ریسک دیوار مهربانی",
    ),
    ("kindness_wall", "kindnessduplicatecandidate"): (
        "مورد تکراری احتمالی دیوار مهربانی",
        "موارد تکراری احتمالی دیوار مهربانی",
    ),

    # LMS
    ("lms", "lmscategory"): ("دسته‌بندی آموزش", "دسته‌بندی‌های آموزش"),
    ("lms", "course"): ("دوره آموزشی", "دوره‌های آموزشی"),
    ("lms", "lesson"): ("جلسه آموزشی", "جلسات آموزشی"),
    ("lms", "learningactivitystatement"): (
        "رویداد فعالیت آموزشی",
        "رویدادهای فعالیت آموزشی",
    ),
    ("lms", "lessonvideoprocessingjob"): (
        "کار پردازش ویدئوی درس",
        "کارهای پردازش ویدئوی درس",
    ),
    ("lms", "enrollment"): ("ثبت‌نام دوره", "ثبت‌نام‌های دوره"),
    ("lms", "lessonprogress"): ("پیشرفت جلسه", "پیشرفت جلسات"),
    ("lms", "lessonquestion"): ("سؤال جلسه", "سؤالات جلسات"),
    ("lms", "lessonanswer"): ("پاسخ سؤال جلسه", "پاسخ‌های سؤالات جلسات"),
    ("lms", "lessondiscussionreport"): (
        "گزارش تخلف گفتگوی آموزشی",
        "گزارش‌های تخلف گفتگوی آموزشی",
    ),
    ("lms", "quiz"): ("آزمون دوره", "آزمون‌های دوره"),
    ("lms", "quizquestion"): ("سؤال آزمون", "سؤالات آزمون"),
    ("lms", "quizoption"): ("گزینه آزمون", "گزینه‌های آزمون"),
    ("lms", "quizattempt"): ("تلاش آزمون", "تلاش‌های آزمون"),
    ("lms", "quizanswer"): ("پاسخ آزمون", "پاسخ‌های آزمون"),
    ("lms", "quizunlock"): ("بازگشایی آزمون", "بازگشایی‌های آزمون"),
    ("lms", "certificate"): ("گواهی آموزشی", "گواهی‌های آموزشی"),
    ("lms", "lmsuserskill"): ("مهارت آموزشی کاربر", "مهارت‌های آموزشی کاربران"),

    # Madadkar
    ("madadkar", "sponsor"): ("مددکار", "مددکاران"),
    ("madadkar", "campaign"): ("حرکت", "حرکت‌ها"),
    ("madadkar", "campaignimage"): ("تصویر گالری حرکت", "تصاویر گالری حرکت‌ها"),
    ("madadkar", "participation"): ("مشارکت", "مشارکت‌ها"),
    ("madadkar", "payment"): ("پرداخت", "پرداخت‌ها"),
    ("madadkar", "paymentevent"): ("رویداد پرداخت", "رویدادهای پرداخت"),
    ("madadkar", "paymentrefund"): ("بازپرداخت مددکار", "بازپرداخت‌های مددکار"),
    ("madadkar", "campaignfinancialadjustment"): (
        "اصلاح مالی حرکت",
        "اصلاحات مالی حرکت‌ها",
    ),
    ("madadkar", "madadkarfinancialcontrolsnapshot"): (
        "نمای کنترل مالی مددکار",
        "نماهای کنترل مالی مددکار",
    ),
    ("madadkar", "campaigndisbursement"): (
        "تخصیص مالی حرکت",
        "تخصیص‌های مالی حرکت‌ها",
    ),
    ("madadkar", "donationreceipt"): (
        "رسید مشارکت مددکار",
        "رسیدهای مشارکت مددکار",
    ),
    ("madadkar", "madadkarrisksignal"): (
        "سیگنال ریسک مددکار",
        "سیگنال‌های ریسک مددکار",
    ),
    ("madadkar", "paymentreconciliationbatch"): (
        "دسته تطبیق پرداخت",
        "دسته‌های تطبیق پرداخت",
    ),
    ("madadkar", "paymentreconciliationitem"): (
        "ردیف تطبیق پرداخت",
        "ردیف‌های تطبیق پرداخت",
    ),

    # Public reports
    ("public_reports", "reportsubject"): ("موضوع گزارش", "موضوعات گزارش"),
    ("public_reports", "report"): ("گزارش مردمی", "گزارش‌های مردمی"),
    ("public_reports", "reportattachment"): ("مستند گزارش", "مستندات گزارش‌ها"),

    # Support desk
    ("support_desk", "supportdepartment"): (
        "دپارتمان پشتیبانی",
        "دپارتمان‌های پشتیبانی",
    ),
    ("support_desk", "supportcategory"): (
        "دسته‌بندی پشتیبانی",
        "دسته‌بندی‌های پشتیبانی",
    ),
    ("support_desk", "supportbusinesscalendar"): (
        "تقویم کاری پشتیبانی",
        "تقویم‌های کاری پشتیبانی",
    ),
    ("support_desk", "supportholiday"): ("تعطیلی پشتیبانی", "تعطیلی‌های پشتیبانی"),
    ("support_desk", "supportslapolicy"): (
        "سیاست سطح خدمت پشتیبانی",
        "سیاست‌های سطح خدمت پشتیبانی",
    ),
    ("support_desk", "supporttickettype"): (
        "نوع تیکت پشتیبانی",
        "انواع تیکت پشتیبانی",
    ),
    ("support_desk", "supportticket"): ("تیکت پشتیبانی", "تیکت‌های پشتیبانی"),
    ("support_desk", "supportticketmessage"): (
        "پیام تیکت پشتیبانی",
        "پیام‌های تیکت پشتیبانی",
    ),
    ("support_desk", "supportticketattachment"): (
        "ضمیمه تیکت پشتیبانی",
        "ضمیمه‌های تیکت پشتیبانی",
    ),
    ("support_desk", "supporttag"): ("تگ پشتیبانی", "تگ‌های پشتیبانی"),
    ("support_desk", "supporttickettag"): ("تگ تیکت پشتیبانی", "تگ‌های تیکت پشتیبانی"),
    ("support_desk", "supportcannedresponse"): (
        "پاسخ آماده پشتیبانی",
        "پاسخ‌های آماده پشتیبانی",
    ),
    ("support_desk", "supportknowledgearticle"): (
        "مقاله پایگاه دانش پشتیبانی",
        "مقالات پایگاه دانش پشتیبانی",
    ),
    ("support_desk", "supportknowledgearticleuse"): (
        "استفاده از مقاله پایگاه دانش",
        "استفاده‌های مقاله پایگاه دانش",
    ),
    ("support_desk", "supportticketassignment"): (
        "ارجاع تیکت پشتیبانی",
        "ارجاع‌های تیکت پشتیبانی",
    ),
    ("support_desk", "supportticketstatushistory"): (
        "تاریخچه وضعیت تیکت",
        "تاریخچه‌های وضعیت تیکت",
    ),
    ("support_desk", "supportslaevent"): (
        "رویداد سطح خدمت پشتیبانی",
        "رویدادهای سطح خدمت پشتیبانی",
    ),
    ("support_desk", "supportticketsatisfaction"): (
        "رضایت‌سنجی تیکت",
        "رضایت‌سنجی‌های تیکت",
    ),
    ("support_desk", "supportduplicatecandidate"): (
        "تیکت تکراری احتمالی",
        "تیکت‌های تکراری احتمالی",
    ),
}


def apply_persian_admin_labels() -> None:
    """Apply Persian app/model labels for a consistent Django admin index."""
    for app_label, verbose_name in APP_VERBOSE_NAMES.items():
        try:
            apps.get_app_config(app_label).verbose_name = verbose_name
        except LookupError:
            continue

    for (app_label, model_name), (verbose_name, verbose_name_plural) in MODEL_VERBOSE_NAMES.items():
        try:
            model = apps.get_model(app_label, model_name)
        except LookupError:
            continue
        model._meta.verbose_name = verbose_name
        model._meta.verbose_name_plural = verbose_name_plural
