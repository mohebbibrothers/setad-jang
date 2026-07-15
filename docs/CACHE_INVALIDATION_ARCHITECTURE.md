# Setad Jang Public Cache Invalidation Architecture

This project uses a production-grade, event-driven cache invalidation system for
public data shown by the frontend.

## Goals

- Cache aggressively for public read paths.
- Invalidate precisely after writes.
- Keep backend mutations reliable even when the frontend is temporarily down.
- Make invalidation observable and operable.

## Core building blocks

### Cache policy registry

`apps/core/cache_policy.py` defines each public domain:

- backend cache namespaces
- frontend tags
- frontend paths
- soft TTL
- hard TTL
- dogpile lock TTL

Current domains:

- `r4j`
- `tabyin`
- `madadkar`
- `lms`
- `kindness`
- `public_reports`

### SWR cache helper

`apps/core/cache.py` exposes `cache_get_or_set_swr()`:

- fresh values are returned until soft TTL
- stale values can be served until hard TTL
- a lock prevents cache stampedes
- refresh failures serve stale data when possible

### Durable invalidation outbox

`apps/core/models.py::CacheInvalidationEvent` stores frontend revalidation work:

- `pending`
- `processing`
- `succeeded`
- `failed`
- `dead`

This prevents write flows from depending on immediate frontend availability.

### Celery processing

`apps/core/tasks.py` contains:

- `revalidate_frontend_task`
- `process_cache_invalidation_event_task`
- `process_pending_cache_invalidation_events_task`

The batch processor is scheduled by Celery Beat every minute.

### Frontend endpoint

The frontend exposes:

```text
POST /api/revalidate
```

It accepts validated `tags` and `paths` and requires `REVALIDATE_SECRET`.

## Environment variables

Backend:

```text
CACHE_INVALIDATION_OUTBOX_ENABLED=True
CACHE_INVALIDATION_MAX_ATTEMPTS=10
CACHE_INVALIDATION_BATCH_SIZE=100
FRONTEND_REVALIDATION_ENABLED=True
FRONTEND_REVALIDATION_URL=https://example.com/api/revalidate
FRONTEND_REVALIDATION_SECRET=<same-secret-as-frontend>
FRONTEND_REVALIDATION_TIMEOUT=5
```

Frontend:

```text
REVALIDATE_SECRET=<same-secret-as-backend>
```

## Mutation flow

1. Public-facing model changes.
2. Service/signal calls `invalidate_public_domain(domain)`.
3. Backend namespace versions are incremented.
4. A `CacheInvalidationEvent` is persisted after DB commit.
5. Celery processes the event and calls the frontend revalidation endpoint.
6. Next.js invalidates tags/paths.
7. The next frontend request rebuilds with fresh backend data.

## Operational admin

`CacheInvalidationEvent` is registered in Django admin. Operators can:

- inspect attempts and errors
- retry selected events
- mark events dead
- move failed/dead events back to pending

## Production notes

- Prefer Redis for backend cache.
- Prefer CDN/object storage or web-server aliases for public media.
- Keep `SERVE_PUBLIC_MEDIA=False` in real production unless this Django fallback
  is explicitly intended.
- Alert on growing pending/failed/dead outbox events.
