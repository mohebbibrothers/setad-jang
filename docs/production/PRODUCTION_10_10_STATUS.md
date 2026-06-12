# Production 10/10 Status

This document tracks the final production excellence roadmap.

## Completed

```text
Dependency/security gate
pip-audit
Bandit production scan
detect-secrets baseline
Structured JSON logging
Request ID correlation
Prometheus metrics endpoint
HTTP and Celery metrics
Sentry env-driven hook
OpenTelemetry tracer provider hook
S3/MinIO storage contracts
CDN/custom domain support
Private signed URL storage
File security scanner contract
Provider readiness for email/SMS/payment
Coverage gate
Cross-app quality tests
Runbooks and operational docs
```

## External dependencies still requiring real-world credentials/licenses

```text
SMS provider license/API key
Zarinpal merchant id
Brevo/domain SMTP verification
Production object storage bucket/CDN
Production database/Redis managed infrastructure
```

## Current policy

Until licensed providers are available:

```text
SMS remains console/dev or HTTP adapter with no real credential
Madadkar payments use sandbox provider
Email uses readable console in development and Brevo-ready SMTP in production
```

## Next recommended real-world steps

```text
Revoke/rotate any GitHub token pasted outside secret manager
Provision production Postgres/Redis
Provision S3/MinIO bucket and optional CDN
Verify Brevo domain SPF/DKIM
Obtain SMS provider license and configure HTTP adapter or custom adapter
Obtain Zarinpal merchant id and switch env from sandbox to zarinpal
Run staging deployment drill
Run backup/restore drill
Run load test
```
