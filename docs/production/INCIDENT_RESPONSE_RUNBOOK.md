# Incident Response Runbook

## 1. Incident severity

| Severity | Example | Response |
|---|---|---|
| SEV1 | data leak, payment corruption, total outage | immediate all-hands |
| SEV2 | login outage, payment provider outage, DB degraded | urgent |
| SEV3 | partial feature degradation | normal incident |
| SEV4 | cosmetic/minor issue | backlog |

## 2. First 10 minutes

1. Freeze deploys.
2. Identify last deployed git SHA.
3. Check `/api/v1/health/detailed/`.
4. Check `/api/v1/metrics/`.
5. Check worker/beat/Flower.
6. Check PostgreSQL/Redis health.
7. Check Sentry/errors/logs.
8. Assign incident commander.

## 3. Data/security incidents

If token/secret leaked:

```text
revoke immediately
rotate credential
invalidate sessions if auth-related
audit logs for abuse
force redeploy with new env
write postmortem
```

If payment issue:

```text
freeze payment verification if corruption suspected
export payment ledger
compare provider ref_id/authority/amount
keep immutable payment events
contact payment provider
```

If media leak:

```text
revoke public object ACL
rotate signed URL keys if applicable
review object storage bucket policy
```

## 4. Communication

Keep an incident timeline:

```text
time detected
impact
mitigation
owner
next update
resolution
postmortem link
```

## 5. Postmortem

Every SEV1/SEV2 requires:

```text
root cause
what detected it
what missed it
customer impact
timeline
corrective actions
owner/date
```
