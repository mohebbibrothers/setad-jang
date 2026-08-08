"""Regression tests for the global Django admin dual-calendar enhancement."""

from __future__ import annotations

from pathlib import Path

from django.template.loader import render_to_string

BASE_DIR = Path(__file__).resolve().parents[3]


def test_admin_base_site_loads_dual_calendar_assets():
    """The admin base template must load the project-wide calendar CSS/JS."""
    template = (BASE_DIR / "templates" / "admin" / "base_site.html").read_text()

    assert "core/admin_dual_calendar.css" in template
    assert "core/admin_dual_calendar.js" in template
    assert "admin/base.html" in template


def test_dual_calendar_javascript_has_jalali_and_gregorian_support_without_external_assets():
    """The JavaScript must be self-contained and expose both calendar modes."""
    script = (BASE_DIR / "apps" / "core" / "static" / "core" / "admin_dual_calendar.js").read_text()

    assert "gregorianToJalali" in script
    assert "jalaliToGregorian" in script
    assert "useInlinePopover" in script
    assert ".inline-group, .inline-related" in script
    assert "viewport clamping" in script
    assert "getBoundingClientRect" in script
    assert "شمسی" in script
    assert "میلادی" in script
    assert "تقویم پیشرفته" in script
    assert "http://" not in script
    assert "https://" not in script


def test_dual_calendar_css_is_available_and_scoped():
    """The CSS should be scoped to sj-date classes to avoid admin-wide regressions."""
    css = (BASE_DIR / "apps" / "core" / "static" / "core" / "admin_dual_calendar.css").read_text()

    assert ".sj-date-popover" in css
    assert ".sj-date-popover-inline" in css
    assert ".sj-date-trigger" in css
    assert "position: fixed" in css
    assert "max-height: min(86vh, 620px)" in css


def test_admin_base_site_template_renders_without_context_errors():
    """A minimal render protects against broken admin template overrides."""
    html = render_to_string(
        "admin/base_site.html",
        {
            "title": "Test",
            "site_title": "Admin",
            "site_header": "Admin",
            "user": type("AnonymousLike", (), {"is_anonymous": True})(),
        },
    )

    assert "admin_dual_calendar.js" in html
    assert "admin_dual_calendar.css" in html
