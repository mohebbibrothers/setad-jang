# Release Checklist

## 1. Before merge/deploy

```bash
git fetch origin main
git status --short --branch
make verify
```

Must be clean:

```text
pip-audit
bandit
detect-secrets
ruff
migration drift
OpenAPI schema
coverage threshold
full tests
```

## 2. Release notes

Each release must state:

```text
git SHA
apps affected
migrations yes/no
settings/env changes
provider changes
rollback risk
manual smoke checklist
```

## 3. Migration policy

- Prefer backward-compatible migrations.
- Avoid destructive migrations without backup.
- For high-risk migrations, run staging restore drill first.

## 4. Smoke tests by app

```text
Auth: signup/login/OTP/profile
Public reports: subject list + report tracking
Tabyin: public list + manual incremental sync
Audit logs: admin log list
R4J: public criminal list + user report
Madadkar: campaign list + sandbox payment flow
LMS: course list + enrollment + certificate verify
Kindness Wall: listings + reveal contact auth boundary
Support Desk: create/submit/reply ticket
```

## 5. Rollback checklist

```text
previous image available
database backup available
migration reversibility known
provider credentials unchanged or reversible
health endpoints green after rollback
```
