"""Regression tests ensuring R4J remains focused on criminals, reports, and bounties.

Investigation/operational case management was intentionally removed from R4J.
The app is now only responsible for publishing criminal profiles, collecting
community reports/evidence, and managing bounty commitments.
"""

from __future__ import annotations

import pytest
from django.apps import apps
from django.urls import NoReverseMatch, reverse

pytestmark = pytest.mark.django_db


REMOVED_CASE_ROUTE_NAMES = (
    "admin-case-list",
    "admin-case-create-from-report",
    "admin-case-detail",
    "admin-case-triage",
    "admin-case-assign",
    "admin-case-priority",
    "admin-case-request-evidence",
    "admin-case-escalate",
    "admin-case-resolve",
    "admin-case-reject",
    "admin-case-close",
    "admin-case-reopen",
    "admin-case-timeline",
    "admin-case-operations-overview",
)


def test_r4j_investigation_case_models_are_removed_from_app_registry():
    """The case-management tables/models must not be part of active R4J anymore."""
    with pytest.raises(LookupError):
        apps.get_model("r4j", "R4JInvestigationCase")

    with pytest.raises(LookupError):
        apps.get_model("r4j", "R4JCaseEvent")


def test_r4j_case_api_routes_are_removed():
    """No case-management endpoint should remain addressable under the R4J API."""
    kwargs_by_name = {
        "admin-case-create-from-report": {"report_id": 1},
        "admin-case-detail": {"case_number": "R4J-20260720-000001"},
        "admin-case-triage": {"case_number": "R4J-20260720-000001"},
        "admin-case-assign": {"case_number": "R4J-20260720-000001"},
        "admin-case-priority": {"case_number": "R4J-20260720-000001"},
        "admin-case-request-evidence": {"case_number": "R4J-20260720-000001"},
        "admin-case-escalate": {"case_number": "R4J-20260720-000001"},
        "admin-case-resolve": {"case_number": "R4J-20260720-000001"},
        "admin-case-reject": {"case_number": "R4J-20260720-000001"},
        "admin-case-close": {"case_number": "R4J-20260720-000001"},
        "admin-case-reopen": {"case_number": "R4J-20260720-000001"},
        "admin-case-timeline": {"case_number": "R4J-20260720-000001"},
    }

    for name in REMOVED_CASE_ROUTE_NAMES:
        with pytest.raises(NoReverseMatch):
            reverse(f"r4j:{name}", kwargs=kwargs_by_name.get(name))


def test_core_r4j_routes_remain_available_after_case_removal():
    """Removing cases must not affect criminals, reports, custody, or bounty routes."""
    assert reverse("r4j:public-criminal-list") == "/api/v1/r4j/criminals/"
    assert (
        reverse("r4j:user-report-submit", kwargs={"criminal_id": 1})
        == "/api/v1/r4j/criminals/1/reports/"
    )
    assert (
        reverse("r4j:user-bounty-set", kwargs={"criminal_id": 1})
        == "/api/v1/r4j/criminals/1/bounty/"
    )
    assert reverse("r4j:admin-report-list") == "/api/v1/r4j/admin/reports/"
    assert reverse("r4j:admin-bounty-list") == "/api/v1/r4j/admin/bounties/"
    assert reverse("r4j:admin-evidence-custody-list") == "/api/v1/r4j/admin/evidence-custody/"
