# Cache/Revalidation Deployment Checklist

This checklist is the operational runbook for enabling the production-grade
public cache invalidation system.

## 1. Required backend environment

```env
CACHE_INVALIDATION_OUTBOX_ENABLED=True
CACHE_INVALIDATION_MAX_ATTEMPTS=10
CACHE_INVALIDATION_BATCH_SIZE=100

FRONTEND_REVALIDATION_ENABLED=True
FRONTEND_REVALIDATION_URL=https://<frontend-host>/api/revalidate
FRONTEND_REVALIDATION_SECRET=<same-strong-secret-as-frontend>
FRONTEND_REVALIDATION_TIMEOUT=5
```

For the isolated HTTP demo, the URL may be:

```env
FRONTEND_REVALIDATION_URL=http://188.253.2.86:3000/api/revalidate
```

## 2. Required frontend environment

```env
REVALIDATE_SECRET=<same-strong-secret-as-backend>
```

## 3. Deployment order

1. Deploy frontend code containing `POST /api/revalidate`.
2. Set `REVALIDATE_SECRET` on the frontend runtime.
3. Deploy backend code containing the outbox/revalidation tasks.
4. Set backend revalidation env vars.
5. Run database migrations.
6. Restart backend web and worker/beat processes.
7. Restart frontend only if its runtime env changed.

## 4. Smoke test

### Backend health

```bash
curl -fsS http://127.0.0.1:18080/api/v1/health/ready/
```

### Frontend revalidation endpoint authorization

```bash
curl -i -X POST http://127.0.0.1:3000/api/revalidate \
  -H 'content-type: application/json' \
  -H "authorization: Bearer $REVALIDATE_SECRET" \
  -d '{"tags":["homepage"],"paths":["/"]}'
```

Expected: `200` and `success: true`.

### End-to-end mutation test

1. Change a public R4J/Tabyin/Madadkar/LMS/Kindness/PublicReports object.
2. Verify a `CacheInvalidationEvent` is created.
3. Verify it reaches `succeeded`.
4. Refresh the frontend page and confirm fresh data appears.

## 5. Admin operations

The Django admin exposes `CacheInvalidationEvent` with actions to:

- retry selected events
- mark selected events as dead
- move failed/dead events back to pending

## 6. Metrics to watch

- `setadjang_cache_operations_total`
- `setadjang_cache_invalidations_total`
- `setadjang_frontend_revalidations_total`
- `setadjang_frontend_revalidation_duration_seconds`
- `setadjang_cache_invalidation_outbox_events`
- `setadjang_cache_invalidation_outbox_oldest_pending_seconds`

## 7. Rollback

If frontend revalidation is misconfigured, disable only the outbound integration:

```env
FRONTEND_REVALIDATION_ENABLED=False
```

Backend cache invalidation will still occur through namespace versioning; the
frontend will fall back to normal ISR TTL behavior.

If the outbox processor causes operational noise, temporarily disable durable
outbox creation:

```env
CACHE_INVALIDATION_OUTBOX_ENABLED=False
```

Use this only as an emergency switch; the preferred production mode keeps the
outbox enabled.
