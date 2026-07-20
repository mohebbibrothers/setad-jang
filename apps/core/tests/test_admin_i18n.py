"""Tests for centralized Persian Django admin labels."""

from __future__ import annotations

from apps.core.admin_i18n import APP_VERBOSE_NAMES, MODEL_VERBOSE_NAMES

ENGLISH_ADMIN_TERMS = (
    "Blacklist",
    "Blacklisted",
    "Outstanding",
    "Token",
    "Notification",
    "Kindness",
    "Support",
    "Learning",
    "Job",
    "Batch",
    "Snapshot",
    "Model name",
)


def test_admin_app_labels_are_persian_for_known_english_apps():
    assert APP_VERBOSE_NAMES["token_blacklist"] == "مدیریت توکن‌ها"
    assert APP_VERBOSE_NAMES["auth"] == "دسترسی‌ها و گروه‌ها"


def test_admin_model_labels_cover_known_english_model_names():
    required_keys = {
        ("token_blacklist", "blacklistedtoken"),
        ("token_blacklist", "outstandingtoken"),
        ("notifications", "notificationdelivery"),
        ("notifications", "notificationevent"),
        ("notifications", "notificationpreference"),
        ("notifications", "notificationtemplate"),
        ("kindness_wall", "kindnessbookmark"),
        ("kindness_wall", "kindnessduplicatecandidate"),
        ("lms", "learningactivitystatement"),
        ("lms", "lessonvideoprocessingjob"),
        ("madadkar", "paymentreconciliationbatch"),
        ("madadkar", "madadkarfinancialcontrolsnapshot"),
        ("support_desk", "supportduplicatecandidate"),
        ("support_desk", "supportslaevent"),
        ("support_desk", "supportticketassignment"),
        ("support_desk", "supportticketsatisfaction"),
        ("support_desk", "supportticketstatushistory"),
    }

    assert required_keys <= MODEL_VERBOSE_NAMES.keys()


def test_curated_admin_labels_do_not_expose_common_english_admin_terms():
    all_labels = [*APP_VERBOSE_NAMES.values()]
    for verbose_name, verbose_name_plural in MODEL_VERBOSE_NAMES.values():
        all_labels.extend([verbose_name, verbose_name_plural])

    offenders = {
        label: term
        for label in all_labels
        for term in ENGLISH_ADMIN_TERMS
        if term.lower() in label.lower()
    }

    assert offenders == {}
