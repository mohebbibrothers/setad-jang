"""Settings-time observability bootstrap helpers."""

from __future__ import annotations


def bootstrap_observability(
    *,
    sentry_dsn: str,
    sentry_environment: str,
    sentry_traces_sample_rate: float,
    sentry_profiles_sample_rate: float,
    otel_enabled: bool,
    otel_service_name: str,
) -> None:
    """Initialize optional observability integrations from settings values."""
    from apps.core.observability import initialize_opentelemetry, initialize_sentry

    initialize_sentry(
        dsn=sentry_dsn,
        environment=sentry_environment,
        traces_sample_rate=sentry_traces_sample_rate,
        profiles_sample_rate=sentry_profiles_sample_rate,
    )
    initialize_opentelemetry(service_name=otel_service_name, enabled=otel_enabled)
