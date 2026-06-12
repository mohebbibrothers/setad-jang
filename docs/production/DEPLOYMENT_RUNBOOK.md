# Deployment Runbook — Setad Jang

## 1. Pre-deployment gate

Every deployment must pass:

```bash
git status --short --branch
make verify
```

This includes:

```text
pip check
pip-audit
bandit
detect-secrets
ruff
Django check
deploy check
migration drift check
OpenAPI validation
pytest with coverage threshold
```

## 2. Build image

```bash
docker-compose build web worker beat
```

Production image uses:

```text
multi-stage build
wheel cache stage
tini
gosu privilege drop
readiness healthcheck
non-root runtime after entrypoint bootstrap
```

## 3. Deploy order

1. Provision/verify PostgreSQL.
2. Provision/verify Redis.
3. Configure `.env` from `ENVIRONMENT_MATRIX.md`.
4. Build and publish image.
5. Run web with `RUN_MIGRATIONS=1` exactly once per release.
6. Run collectstatic if static assets changed.
7. Start worker and beat.
8. Verify health endpoints.
9. Verify metrics endpoint.
10. Run smoke tests.

## 4. Docker compose local production-like

```bash
cp .env.example .env
# edit .env
POSTGRES_PASSWORD=<strong-password> docker-compose up --build -d
```

## 5. Smoke checklist

```bash
curl -fsS http://127.0.0.1:8000/api/v1/health/
curl -fsS http://127.0.0.1:8000/api/v1/health/ready/
curl -fsS http://127.0.0.1:8000/api/v1/health/detailed/
curl -fsS http://127.0.0.1:8000/api/v1/metrics/
```

Manual app smoke:

```text
Auth signup/login OTP flow
Tabyin public content list
Madadkar public campaigns
LMS public courses
Kindness Wall public listings
Support Desk authenticated ticket creation
Admin dashboard access
```

## 6. Rollback

Rollback must be planned before deployment.

1. Keep previous image tag.
2. Check whether migrations are backward-compatible.
3. If migration is not reversible, restore database backup.
4. Redeploy previous image.
5. Verify health and smoke checks.

## 7. Post-deployment monitoring

Watch for:

```text
HTTP 5xx rate
request latency
Celery task failures
DB latency
Redis latency
SLA breach spike
payment failures
OTP delivery failures
```

Use:

```text
/api/v1/metrics/
/api/v1/health/detailed/
Flower
Sentry
structured JSON logs
```
