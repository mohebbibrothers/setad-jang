"""
AppConfig for the LMS application.

LMS (Learning Management System) is the education domain of Setad Jang: dynamic
categories, courses, lessons, enrollments, progress tracking, Q&A, professional
quizzes, certificates, and skill badges.
"""

from django.apps import AppConfig


class LMSConfig(AppConfig):
    """Application configuration for the LMS domain."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.lms"
    verbose_name = "سامانه آموزش بعثت مردم"

    def ready(self) -> None:
        """Register public cache invalidation signal handlers."""
        from . import signals  # noqa: F401

