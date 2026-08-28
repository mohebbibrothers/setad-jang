"""Optional production observability integrations.

This module keeps Sentry/OpenTelemetry initialization defensive and env-driven so
local development and CI do not require external observability services.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("apps.core.observability")


def initialize_sentry(
    *,
    dsn: str,
    environment: str,
    traces_sample_rate: float = 0.0,
    profiles_sample_rate: float = 0.0,
) -> bool:
    """Initialize Sentry if DSN is configured."""
    if not dsn:
        return False
    try:
        import sentry_sdk
    except ImportError:  # pragma: no cover - dependency is installed in production requirements
        logger.warning("Sentry DSN configured but sentry-sdk is not installed.")
        return False
    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        traces_sample_rate=traces_sample_rate,
        profiles_sample_rate=profiles_sample_rate,
        send_default_pii=False,
    )
    logger.info("Sentry initialized environment=%s", environment)
    return True


def initialize_opentelemetry(*, service_name: str, enabled: bool) -> bool:
    """Initialize OpenTelemetry tracer provider when enabled.

    Exporter wiring is intentionally environment-specific and will be extended in
    the deployment layer. This function establishes a named tracer provider so
    instrumentation can be added without touching business code.
    """
    if not enabled:
        return False
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
    except ImportError:  # pragma: no cover - dependency is installed in production requirements
        logger.warning("OpenTelemetry enabled but opentelemetry packages are not installed.")
        return False
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    trace.set_tracer_provider(provider)
    logger.info("OpenTelemetry tracer provider initialized service=%s", service_name)
    return True
