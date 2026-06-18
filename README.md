# ستاد جنگ — Setad Jang Enterprise Backend

<p align="center">
  <strong>Enterprise-grade, production-minded Django REST Framework backend</strong><br />
  Django 6 · DRF · PostgreSQL · Redis · Celery · OpenAPI · JWT · Audit Trail · LMS · Kindness Wall · Support Desk
</p>

<p align="center">
  <img alt="Django" src="https://img.shields.io/badge/Django-6.x-0C4B33?style=for-the-badge&logo=django&logoColor=white" />
  <img alt="DRF" src="https://img.shields.io/badge/DRF-3.x-A30000?style=for-the-badge" />
  <img alt="PostgreSQL" src="https://img.shields.io/badge/PostgreSQL-production-4169E1?style=for-the-badge&logo=postgresql&logoColor=white" />
  <img alt="Redis" src="https://img.shields.io/badge/Redis-cache%20%2B%20broker-DC382D?style=for-the-badge&logo=redis&logoColor=white" />
  <img alt="Celery" src="https://img.shields.io/badge/Celery-worker%20%2B%20beat-37814A?style=for-the-badge&logo=celery&logoColor=white" />
  <img alt="Tests" src="https://img.shields.io/badge/tests-1118%2B%20passed-brightgreen?style=for-the-badge" />
  <img alt="Security" src="https://img.shields.io/badge/security-pip--audit%20%2B%20bandit%20%2B%20detect--secrets-blue?style=for-the-badge" />
</p>

---

## 0. فهرست سریع

- [1. هدف پروژه](#1-هدف-پروژه)
- [2. وضعیت کیفیت فعلی](#2-وضعیت-کیفیت-فعلی)
- [3. معماری کلان](#3-معماری-کلان)
- [4. نصب و اجرای Local](#4-نصب-و-اجرای-local)
- [5. Docker و Runtime](#5-docker-و-runtime)
- [6. Quality / Security / CI](#6-quality--security--ci)
- [7. API Documentation](#7-api-documentation)
- [8. Core Infrastructure](#8-core-infrastructure)
- [9. Authentication](#9-authentication)
- [10. Public Reports](#10-public-reports)
- [11. Tabyin](#11-tabyin)
- [12. Audit Logs](#12-audit-logs)
- [13. R4J](#13-r4j)
- [14. Madadkar](#14-madadkar)
- [15. LMS](#15-lms)
- [16. Kindness Wall](#16-kindness-wall)
- [17. Support Desk](#17-support-desk)
- [18. Redis / Cache / Celery / Observability](#18-redis--cache--celery--observability)
- [19. Providers: SMS / Payment / Email](#19-providers-sms--payment--email)
- [20. Production Runbooks](#20-production-runbooks)
- [21. Production Checklist](#21-production-checklist)
- [22. فلسفه مهندسی](#22-فلسفه-مهندسی)

---

## 1. هدف پروژه

**Setad Jang** یک backend چنددامنه‌ای، ماژولار، API-first و production-minded است. هدف آن فقط ساخت چند endpoint نیست؛ هدف، نمایش یک backend قابل دفاع در سطح senior/enterprise است:

```text
Architecture discipline
Security by default
Service-layer mutations
Selector-layer reads
Auditability
Operational readiness
Observability hooks
Performance contracts
Admin-grade analytics/export
CI/CD quality gates
```

اصل محوری:

> View فقط مرز HTTP است. هر mutation باید از service layer و هر read مهم باید از selector layer عبور کند.

---

## 2. وضعیت کیفیت فعلی

آخرین verification موفق:

```bash
make verify
```

خروجی مورد انتظار:

```text
python -m pip check                              ✅ No broken requirements
python -m pip_audit                              ✅ No known vulnerabilities
python -m bandit                                 ✅ Clean production SAST gate
detect-secrets scan                              ✅ Baseline-controlled secret scan
python -m ruff check .                           ✅ All checks passed
python manage.py check                           ✅ No issues
python manage.py check --deploy                  ✅ No issues
python manage.py makemigrations --check --dry-run ✅ No changes detected
python manage.py spectacular --validate          ✅ Clean OpenAPI schema
python -m pytest with coverage gate                              ✅ 1118+ passed
```

Policyهای enforced:

```text
Zero-warning policy
No TODO/FIXME/pass/placeholder in production code
No direct database mutation in views
Security gate is part of verify
OpenAPI must validate without warnings
Migration drift is forbidden
Full regression before push
```

---

## 3. معماری کلان

```text
Client / Frontend
      │
      ▼
DRF API Layer
      │
      ├── Views              → HTTP orchestration only
      ├── Serializers        → input/output contracts + validation
      ├── Services           → business workflows, mutations, transactions
      ├── Selectors          → optimized reads, select_related/prefetch_related
      ├── Filters            → query param filtering
      ├── Permissions        → role/ownership boundaries
      ├── Throttles          → abuse/rate protection
      ├── Audit Logs         → forensic trail
      ├── Celery Tasks       → async/scheduled jobs
      └── OpenAPI            → schema-first API docs

PostgreSQL                  → production DB
Redis                       → cache + Celery broker/result backend
Celery Worker/Beat          → background and scheduled jobs
Docker Compose              → web/postgres/redis/worker/beat/flower
GitHub Actions              → quality + security gate
```

---

## 4. نصب و اجرای Local

### نصب استاندارد

```bash
python -m venv .venv
source .venv/bin/activate        # Linux/macOS
# Windows PowerShell:
# .venv\Scripts\Activate.ps1

make install
python manage.py migrate
python manage.py runserver
```

### نصب مستقیم بدون Makefile

```bash
python -m pip install -r requirements.txt -r requirements-dev.txt
python manage.py migrate
python manage.py runserver
```

### ساخت ادمین

```bash
python manage.py createsuperuser
```

### اجرای تست‌ها

```bash
make test
pytest with coverage gate
```

---

## 5. Docker و Runtime

سرویس‌ها در `docker-compose.yml`:

```text
web       → Django/Gunicorn
postgres  → PostgreSQL 17
redis     → Redis cache/broker
worker    → Celery worker
beat      → Celery beat
flower    → Celery monitoring UI
```

اجرای local production-like:

```bash
docker-compose up --build -d
```

خاموش کردن:

```bash
docker-compose down
```

Dockerfile:

- multi-stage build
- wheel build در stage جدا
- runtime کوچک‌تر
- `tini` برای signal handling
- `gosu` برای privilege drop
- user غیر-root برای app
- healthcheck روی readiness endpoint:

```text
/api/v1/health/ready/
```

entrypoint:

- آماده‌سازی writable dirs
- wait for Redis
- migrations opt-in با `RUN_MIGRATIONS=1`
- collectstatic opt-in با `RUN_COLLECTSTATIC=1`
- privilege drop به user app

---

## 6. Quality / Security / CI

### دستورهای Makefile

```bash
make install
make lint
make check
make deploy-check
make migrations-check
make schema-check
make schema-update
make pip-check
make pip-audit
make bandit
make secrets-scan
make security
make test
make verify
```

### security gate

```bash
make security
```

اجرا می‌کند:

```text
pip-audit                         dependency vulnerability scan
bandit                            production SAST scan
locally controlled detect-secrets baseline scan
```

### full verify

```bash
make verify
```

اجرا می‌کند:

```text
pip check
security
ruff
Django check
Django deploy check
migration drift check
OpenAPI validate
full pytest with coverage threshold
```

### CI

`.github/workflows/ci.yml` شامل:

- PostgreSQL service
- Redis service
- Python 3.14
- dependency install
- pip check
- security gate
- Ruff
- Django check
- deploy check
- migration drift check
- OpenAPI schema validation
- full pytest with coverage threshold
- schema artifact upload

---

## 7. API Documentation

بعد از اجرای سرور:

```text
Swagger UI : /api/docs/
ReDoc      : /api/redoc/
Schema     : /api/schema/
```

Regenerate committed schema:

```bash
make schema-update
```

---

## 8. Core Infrastructure

اپ `core` زیرساخت مشترک کل پروژه است:

- `BaseModel`: `created_at`, `updated_at`, `is_active`
- active/all managers
- response envelope
- custom pagination
- custom exception handler
- request ID middleware
- cache helpers با namespace versioning
- health checks
- OpenAPI schema helpers


### Cross-App Search Foundation

Apex A1 یک search foundation مشترک اضافه کرده است که برای production روی PostgreSQL از full-text search و trigram similarity استفاده می‌کند و برای local/test روی SQLite به fallback امن `icontains` برمی‌گردد.

فایل اصلی:

```text
apps/core/search.py
```

قابلیت‌ها:

```text
Persian/Arabic query normalization
weighted searchable fields
PostgreSQL SearchVector/SearchRank
pg_trgm TrigramSimilarity
SQLite-safe fallback
bounded query length برای جلوگیری از abuse
shared helper برای Tabyin, Kindness Wall, Support Desk, LMS, R4J, Madadkar
```

PostgreSQL extensions در migration هسته فعال می‌شوند، بدون شکستن SQLite:

```text
pg_trgm
unaccent
```

اپ‌هایی که به search مشترک وصل شده‌اند:

```text
tabyin content search
kindness wall listing search
support desk ticket search
lms course search
r4j criminal search
madadkar campaign search
```

### Response envelope

```json
{
  "success": true,
  "status_code": 200,
  "message": "عملیات با موفقیت انجام شد.",
  "data": {}
}
```

### Error envelope

```json
{
  "success": false,
  "status_code": 400,
  "message": "درخواست نامعتبر است.",
  "errors": {}
}
```

### Health endpoints

```text
GET /api/v1/health/live/
GET /api/v1/health/ready/
GET /api/v1/health/detailed/
```

Health checks شامل database/cache/Celery-relevant dependencies است و secret-safe طراحی شده است. detailed health علاوه بر این‌ها وضعیت non-critical provider readiness مثل email/sms/payment را هم بدون ارسال واقعی پیام یا پرداخت گزارش می‌کند.

---

## 9. Authentication

اپ `authentication` احراز هویت چندشناسه‌ای و OTP امن را فراهم می‌کند.

### قابلیت‌ها

- custom user
- email/phone identifiers
- signup with OTP
- login با password
- login با OTP
- forgot/reset password
- add secondary identifier
- make primary identifier
- JWT access/refresh
- tracked device/session registry
- user/admin session revoke workflows
- risk-based authentication signals برای new device/new IP/session anomalies
- admin risk review workflow
- logout/blacklist
- profile completion
- admin user management
- legacy endpoint deprecation

### OTP security

- OTP خام در DB ذخیره نمی‌شود.
- HMAC/SHA256 hashing
- replay protection
- DB-side attempt/cooldown controls
- identifier masking
- provider abstraction برای email/SMS
- anomaly guard
- throttling

### API summary

```text
POST /api/v1/auth/signup/request/
POST /api/v1/auth/signup/verify/
POST /api/v1/auth/login/password/
POST /api/v1/auth/login/otp/request/
POST /api/v1/auth/login/otp/verify/
POST /api/v1/auth/password/forgot/request/
POST /api/v1/auth/password/forgot/confirm/
POST /api/v1/auth/identifiers/add/request/
POST /api/v1/auth/identifiers/add/verify/
POST /api/v1/auth/identifiers/make-primary/
POST /api/v1/auth/token/refresh/
POST /api/v1/auth/logout/
GET  /api/v1/auth/sessions/
POST /api/v1/auth/sessions/{session_id}/revoke/
GET  /api/v1/auth/me/
GET/PATCH /api/v1/auth/profile/
GET  /api/v1/auth/admin/users/
GET  /api/v1/auth/admin/users/{id}/
POST /api/v1/auth/admin/users/{id}/role/
GET  /api/v1/auth/admin/users/{id}/sessions/
POST /api/v1/auth/admin/users/{id}/sessions/revoke-all/
GET  /api/v1/auth/admin/risk-signals/
POST /api/v1/auth/admin/risk-signals/{id}/review/
```

### Disposable email blocklist

Management command:

```bash
python manage.py update_disposable_email_blocklist
```

این command لیست دامنه‌های disposable را به‌روزرسانی می‌کند و برای hardening ثبت‌نام مفید است.

---

## 10. Public Reports

اپ `public_reports` برای ثبت و بررسی گزارشات مردمی است.

### قابلیت‌ها

- subjectهای قابل مدیریت
- ثبت گزارش عمومی/کاربری
- attachment validation
- workflow بررسی ادمین
- privacy-safe public response
- admin list/detail/update/status
- audit-sensitive actions

### Workflow

```text
PENDING   → REVIEWING / APPROVED / REJECTED
REVIEWING → PENDING / APPROVED / REJECTED
APPROVED  → terminal
REJECTED  → terminal
```

### API summary

```text
GET  /api/v1/public-reports/subjects/
POST /api/v1/public-reports/reports/
GET  /api/v1/public-reports/reports/{tracking_code}/
GET  /api/v1/public-reports/admin/subjects/
POST /api/v1/public-reports/admin/subjects/
PATCH/DELETE /api/v1/public-reports/admin/subjects/{id}/
GET  /api/v1/public-reports/admin/reports/
GET  /api/v1/public-reports/admin/reports/{id}/
PATCH /api/v1/public-reports/admin/reports/{id}/
POST /api/v1/public-reports/admin/reports/{id}/status/
```

---

## 11. Tabyin

اپ `tabyin` بانک محتوای جهاد تبیین است؛ شامل محتوای sync شده از provider خارجی و محتوای ارسالی کاربران.

### قابلیت‌ها

- Public content list/detail
- cache سطح selector برای public reads
- sync engine با provider abstraction
- manual admin sync API
- Celery async sync
- incremental/full sync modes
- user submission workflow
- admin submission review
- content toggle publish/archive
- cache invalidation بعد از sync/toggle

### Manual crawl / sync با command line

دو mode رسمی برای crawl دستی وجود دارد:

#### Incremental sync

برای sync سبک و دوره‌ای:

```bash
python manage.py sync_tabyin --mode incremental
```

#### Full sync

برای crawl کامل همه داده‌ها:

```bash
python manage.py sync_tabyin --mode full
```

نمونه PowerShell:

```powershell
python manage.py sync_tabyin --mode incremental
python manage.py sync_tabyin --mode full
```

این command از service/sync engine استفاده می‌کند و خروجی شمارشی از عملیات sync می‌دهد.

### Celery tasks

```text
apps.tabyin.tasks.sync_tabyin_incremental_task
apps.tabyin.tasks.sync_tabyin_full_task
```

Beat schedule:

```text
incremental: every 30 minutes
full: daily at 03:00
```

Queue:

```text
tabyin_sync
```

### API summary

```text
GET  /api/v1/tabyin/contents/
GET  /api/v1/tabyin/contents/{id}/
POST /api/v1/tabyin/me/submissions/
GET  /api/v1/tabyin/me/submissions/
GET  /api/v1/tabyin/me/submissions/{id}/
GET  /api/v1/tabyin/admin/contents/
GET  /api/v1/tabyin/admin/contents/{id}/
POST /api/v1/tabyin/admin/contents/{id}/toggle/
POST /api/v1/tabyin/admin/sync/
GET  /api/v1/tabyin/admin/sync/tasks/{task_id}/
GET  /api/v1/tabyin/admin/submissions/
POST /api/v1/tabyin/admin/submissions/{id}/review/
```

---


## Apex Tamper-Evident Audit Hash Chain

Audit logs include a forensic hash chain:

```text
previous_hash
event_hash
hash_version
```

Verification command:

```bash
python manage.py verify_audit_chain
```

Any direct database tampering with hash-covered fields breaks the chain and is detected by the command.

## 12. Audit Logs

اپ `audit_logs` برای forensic audit trail طراحی شده است: append-only، tamper-evident و incident-response-ready.

### قابلیت‌ها

- append-oriented audit log
- action constants برای همه دامنه‌ها
- async audit dispatch via Celery
- metadata extraction:
  - IP
  - user agent
  - request id
- admin list/detail
- immutability hardening در model/queryset/admin/API
- tamper-evident hash-chain verification
- forensic export package شامل:
  - `manifest.json`
  - `audit_logs.jsonl`
  - `audit_logs.csv`
  - `audit_logs.xlsx`
- SHA-256 digest برای فایل‌های داخل package و header خروجی API
- spreadsheet formula-injection hardening برای CSV/XLSX
- audit شدن خود عملیات export با action `AUDIT_PACKAGE_EXPORTED`
- retention policy محافظه‌کارانه، archive-first و non-destructive به‌صورت پیش‌فرض

### API summary

```text
GET /api/v1/audit-logs/admin/logs/
GET /api/v1/audit-logs/admin/logs/export/
GET /api/v1/audit-logs/admin/logs/{id}/
```

### Forensic commands

```bash
python manage.py verify_audit_chain
python manage.py export_audit_package --output ./audit_exports
python manage.py export_audit_package --output ./audit_exports --action LOGIN_SUCCESS
python manage.py export_audit_package --output ./audit_exports --created-after 2026-06-01T00:00:00Z --created-before 2026-06-16T23:59:59Z
python manage.py audit_retention_report
```

### Retention env

```env
AUDIT_LOG_ARCHIVE_ROOT=/var/lib/setad-jang/audit_exports
AUDIT_LOG_RETENTION_DAYS=2555
AUDIT_LOG_LEGAL_HOLD_ENABLED=True
AUDIT_LOG_RETENTION_DELETE_ENABLED=False
AUDIT_LOG_EXPORT_MAX_RECORDS=100000
```

نکته production: حذف خودکار audit logs عمداً غیرفعال است؛ retention فعلی archive-first است تا در incident response و legal hold هیچ evidence از بین نرود.

---

## 13. R4J

اپ `r4j` سیستم Reward for Justice است.

### قابلیت‌ها

- پروفایل مجرم
- public criminal browse/detail
- گزارش کاربر درباره مجرم
- attachmentها
- admin review گزارش
- field-change workflow
- bounty management
- cancel request/approve/reject
- performance query contracts

### API summary

```text
GET  /api/v1/r4j/criminals/
GET  /api/v1/r4j/criminals/{slug}/
GET  /api/v1/r4j/criminals/{slug}/bounties/
POST /api/v1/r4j/reports/
GET  /api/v1/r4j/me/reports/
GET/PATCH/DELETE /api/v1/r4j/me/reports/{id}/
POST /api/v1/r4j/me/reports/{id}/submit/
POST /api/v1/r4j/me/reports/{id}/cancel-request/
GET/POST /api/v1/r4j/admin/criminals/
GET/PATCH/DELETE /api/v1/r4j/admin/criminals/{id}/
GET /api/v1/r4j/admin/reports/
POST /api/v1/r4j/admin/reports/{id}/review/
GET/POST /api/v1/r4j/admin/bounties/
PATCH/DELETE /api/v1/r4j/admin/bounties/{id}/
```

---


## Apex Madadkar Payment Reconciliation

Madadkar now has finance-grade reconciliation models and services for comparing provider settlement/report rows with internal payment ledger records.

Models:

```text
PaymentReconciliationBatch
PaymentReconciliationItem
```

Classifications:

```text
matched
missing_internal
amount_mismatch
status_mismatch
duplicate_provider_ref
```

Service:

```python
reconcile_provider_payments(provider_name="sandbox", rows=[...], source_name="settlement.csv")
```

This enables future Zarinpal settlement reconciliation without rewriting payment flows.

## 14. Madadkar

اپ `madadkar` سیستم crowdfunding خیریه سهم‌محور است.

### قابلیت‌ها

- sponsor management
- campaign management
- campaign images
- public campaign browse/detail
- share-based participation
- payment initiation
- payment verify callback
- sandbox payment provider
- Zarinpal provider آماده برای بعد از مجوز
- immutable payment event ledger
- provider settlement reconciliation
- refund workflow با request/approve/reject/complete
- campaign financial adjustment workflow با create/approve/reject/apply
- financial-control summary با gross/refunds/adjustments/net amount
- fraud/risk scoring برای payment/refund/adjustment abuse
- campaign intelligence dashboard با net/refund-adjusted metrics، funnel، velocity، donor concentration و health score
- portfolio intelligence overview برای تشخیص ضعیف‌ترین و قوی‌ترین campaignها
- verifiable donation receipts با receipt_number و SHA-256 receipt_hash
- public-safe receipt verification endpoint
- audited receipt access/resend workflow
- settlement CSV/XLSX import و reconciliation API
- discrepancy CSV export برای finance review
- campaign disbursement/allocation ledger برای خروج پول و تخصیص منابع
- disbursable amount calculation با جلوگیری از over-allocation
- public transparency layer برای نمایش امن gross/refund/adjustment/net/disbursed/remaining بدون PII
- financial ops automation/control snapshots برای daily finance review
- scheduled Celery control snapshot و management command برای runbook مالی
- admin risk-signal review workflow
- command center open risk-signal counter
- audit logging برای همه عملیات حساس مالی
- admin analytics
- Excel export participants
- Celery cleanup tasks

### Payment provider modes

تا قبل از گرفتن مجوز Zarinpal:

```env
MADADKAR_PAYMENT_PROVIDER=sandbox
```

بعد از گرفتن merchant id واقعی:

```env
MADADKAR_PAYMENT_PROVIDER=zarinpal
MADADKAR_ZARINPAL_MERCHANT_ID=...
MADADKAR_ZARINPAL_SANDBOX=False
```

کد provider آماده است؛ تغییر اصلی باید در env باشد، نه rewrite کد.

### API summary

```text
GET  /api/v1/madadkar/campaigns/
GET  /api/v1/madadkar/campaigns/{slug}/
POST /api/v1/madadkar/campaigns/{slug}/participate/
POST /api/v1/madadkar/payments/verify/
GET  /api/v1/madadkar/me/participations/
GET  /api/v1/madadkar/admin/sponsors/
POST /api/v1/madadkar/admin/sponsors/
GET/PATCH/DELETE /api/v1/madadkar/admin/sponsors/{id}/
GET/POST /api/v1/madadkar/admin/campaigns/
GET/PATCH/DELETE /api/v1/madadkar/admin/campaigns/{id}/
POST /api/v1/madadkar/admin/campaigns/{id}/publish/
POST /api/v1/madadkar/admin/campaigns/{id}/close/
GET /api/v1/madadkar/admin/campaigns/{id}/analytics/
GET /api/v1/madadkar/admin/campaigns/{id}/export/
GET /api/v1/madadkar/admin/campaigns/{id}/financial-control/
GET/POST /api/v1/madadkar/admin/refunds/
POST /api/v1/madadkar/admin/refunds/{id}/approve/
POST /api/v1/madadkar/admin/refunds/{id}/reject/
POST /api/v1/madadkar/admin/refunds/{id}/complete/
GET/POST /api/v1/madadkar/admin/adjustments/
POST /api/v1/madadkar/admin/adjustments/{id}/approve/
POST /api/v1/madadkar/admin/adjustments/{id}/reject/
POST /api/v1/madadkar/admin/adjustments/{id}/apply/
GET /api/v1/madadkar/admin/risk-signals/
POST /api/v1/madadkar/admin/risk-signals/{id}/review/
GET /api/v1/madadkar/admin/campaigns/{id}/intelligence/
GET /api/v1/madadkar/admin/intelligence/overview/
GET /api/v1/madadkar/me/receipts/
GET /api/v1/madadkar/me/receipts/{id}/
POST /api/v1/madadkar/receipts/verify/
POST /api/v1/madadkar/admin/receipts/{id}/resend/
POST /api/v1/madadkar/admin/reconciliation/import/
GET /api/v1/madadkar/admin/reconciliation/batches/
GET /api/v1/madadkar/admin/reconciliation/batches/{id}/
GET /api/v1/madadkar/admin/reconciliation/batches/{id}/items/
GET /api/v1/madadkar/admin/reconciliation/batches/{id}/export/
GET/POST /api/v1/madadkar/admin/disbursements/
GET /api/v1/madadkar/admin/disbursements/{id}/
POST /api/v1/madadkar/admin/disbursements/{id}/approve/
POST /api/v1/madadkar/admin/disbursements/{id}/reject/
POST /api/v1/madadkar/admin/disbursements/{id}/mark-paid/
GET /api/v1/madadkar/admin/campaigns/{id}/disbursable/
GET /api/v1/madadkar/campaigns/{slug}/transparency/
GET /api/v1/madadkar/admin/financial-controls/
GET /api/v1/madadkar/admin/financial-controls/latest/
POST /api/v1/madadkar/admin/financial-controls/generate/
```

### Celery tasks

```text
apps.madadkar.tasks.expire_stale_participations_task
apps.madadkar.tasks.close_expired_campaigns_task
apps.madadkar.tasks.generate_financial_control_snapshot_task
```

Queue:

```text
madadkar
```

---


## Apex LMS Signed Media Delivery

LMS media delivery now has a dedicated access contract:

```text
GET /api/v1/lms/lessons/{lesson_id}/media/{media_kind}/
```

Supported media kinds:

```text
video
attachment
```

Security and delivery behavior:

```text
non-preview lessons require active/completed enrollment
preview lessons may expose media to authenticated users
uploaded files use Django storage URL; with S3 private storage this becomes signed URL
direct URL and embed lessons are still returned through the same media access contract
each access is audit logged with LMS_LESSON_MEDIA_ACCESSED
CDN/Object Storage flow is ready for uploaded video and handouts
```

## 15. LMS

اپ `lms` سامانه آموزش بعثت مردم است.

### قابلیت‌ها

- category dynamic
- course management
- lessons با content/video metadata
- enrollment رایگان با profile requirement
- progress tracking
- Q&A/discussion
- report discussion
- timed quiz engine
- attempt limit
- pass/fail grading
- certificate PDF
- public certificate verification
- user skills/badges
- admin analytics
- leaderboard
- Excel export participants
- performance contracts

### Quiz rules

- تلاش محدود
- retry policy
- admin unlock
- correct answers hidden until pass/finalization policy

### Certificate

- certificate code
- verification slug
- public verification endpoint
- PDF renderer
- tracked sample certificate asset

### API summary

```text
GET  /api/v1/lms/categories/
GET  /api/v1/lms/categories/{slug}/
GET  /api/v1/lms/courses/
GET  /api/v1/lms/courses/{slug}/
GET  /api/v1/lms/courses/{slug}/lessons/
GET  /api/v1/lms/courses/{slug}/lessons/{lesson_slug}/
POST /api/v1/lms/courses/{slug}/enroll/
GET  /api/v1/lms/courses/{slug}/quiz/
POST /api/v1/lms/courses/{slug}/quiz/start/
GET  /api/v1/lms/quiz/attempts/{id}/
POST /api/v1/lms/quiz/attempts/{id}/submit/
GET  /api/v1/lms/me/enrollments/
GET  /api/v1/lms/me/certificates/
GET  /api/v1/lms/certificates/verify/{slug}/
GET/POST/PATCH/DELETE admin course/category/lesson/quiz/question endpoints
GET  /api/v1/lms/admin/courses/{id}/analytics/
GET  /api/v1/lms/admin/courses/{id}/leaderboard/
GET  /api/v1/lms/admin/courses/{id}/export/
```

---


## Apex Kindness Geo Matching and Risk Signals

Kindness Wall now has geo-aware matching and safety/risk signals:

```text
Haversine distance scoring for listings with lat/lng
nearby_5km / nearby_25km / nearby_75km reason codes
city/province fallback preserved
KindnessRiskSignal model
contact reveal velocity detection
listing contact spike detection
admin risk signal queue foundation
command center open risk signal counter
```

Risk signal types:

```text
contact_reveal_velocity
listing_contact_spike
duplicate_abuse
```

This improves both match quality and human-safety monitoring in the Kindness Wall app.

## 16. Kindness Wall

اپ `kindness_wall` دیوار مهربانی است: آگهی کمک/نیاز بدون خریدوفروش.

### قابلیت‌ها

- دو نوع ثابت listing:
  - need_help
  - offer_help
- dynamic tree categories
- profile completeness requirement
- moderation workflow
- public list/detail بدون شماره تماس
- authenticated contact reveal
- contact reveal audit row
- bookmarks
- reports
- matching engine
- duplicate candidates
- admin analytics
- Excel exports
- N+1 performance contracts

### Privacy rule

Public list/detail هیچ‌وقت `contact_phone_snapshot` را expose نمی‌کند. شماره فقط از endpoint زیر، برای authenticated user، همراه با audit قابل مشاهده است:

```text
POST /api/v1/kindness-wall/listings/{slug}/reveal-contact/
```

### API summary

```text
GET  /api/v1/kindness-wall/categories/
GET  /api/v1/kindness-wall/listings/
GET  /api/v1/kindness-wall/listings/{slug}/
GET  /api/v1/kindness-wall/listings/{slug}/matches/
POST /api/v1/kindness-wall/listings/{slug}/reveal-contact/
POST /api/v1/kindness-wall/listings/{slug}/report/
POST/DELETE /api/v1/kindness-wall/listings/{slug}/bookmark/
GET/POST /api/v1/kindness-wall/me/listings/
GET/PATCH/DELETE /api/v1/kindness-wall/me/listings/{id}/
POST /api/v1/kindness-wall/me/listings/{id}/submit/
POST /api/v1/kindness-wall/me/listings/{id}/renew/
POST /api/v1/kindness-wall/me/listings/{id}/close/
GET /api/v1/kindness-wall/me/bookmarks/
GET /api/v1/kindness-wall/me/matches/
POST /api/v1/kindness-wall/me/matches/{id}/dismiss/
POST /api/v1/kindness-wall/me/matches/{id}/contacted/
GET/POST/PATCH/DELETE admin categories/listings/reports/matches/contact-reveals/duplicates/analytics/export
```

---


## Apex Support Business Hours SLA

Support Desk now supports enterprise business-hours SLA calculation:

```text
SupportBusinessCalendar
SupportHoliday
business_hours_only SLA policies
department-specific calendars
holiday-aware working-minute calculation
admin calendar/holiday APIs
```

Admin APIs:

```text
GET/POST /api/v1/support/admin/business-calendars/
PATCH    /api/v1/support/admin/business-calendars/{calendar_id}/
GET/POST /api/v1/support/admin/holidays/
PATCH    /api/v1/support/admin/holidays/{holiday_id}/
```

When `business_hours_only=True`, first response and resolution deadlines are computed using the resolved business calendar instead of raw wall-clock minutes.

## 17. Support Desk

اپ `support_desk` میز پشتیبانی enterprise است.

### قابلیت‌ها

- dynamic departments
- fully tree-based support categories
- dynamic ticket types/reasons
- SLA policies
- ticket workflow
- user/admin timeline
- internal notes hidden from user
- attachments
- assignment history
- load-balanced assignment recommendation
- auto-assignment بر اساس workload score، SLA pressure و department affinity
- status history
- knowledge base articles با public/help-center API و admin lifecycle
- article recommendation برای ticket subject/description
- smart reply suggestions از ترکیب KB + canned responses + public ticket timeline
- audited smart reply generation/use با exclusion یادداشت‌های داخلی
- audited article usage in support replies/context
- smart triage
- duplicate candidates
- canned responses/macros
- CSAT satisfaction rating
- analytics dashboard
- Excel exports
- SLA breach tasks
- stale draft cleanup
- daily digest task
- performance contracts

### Workflow

```text
DRAFT → SUBMITTED → WAITING_FOR_ADMIN / WAITING_FOR_USER / IN_PROGRESS
      → RESOLVED → CLOSED
      → REOPENED
      → ESCALATED
```

### User API summary

```text
GET    /api/v1/support/departments/
GET    /api/v1/support/categories/
GET    /api/v1/support/ticket-types/
GET    /api/v1/support/knowledge/articles/
GET    /api/v1/support/knowledge/articles/{slug}/
POST   /api/v1/support/knowledge/articles/recommend/
POST   /api/v1/support/me/tickets/suggest/
GET    /api/v1/support/me/tickets/
POST   /api/v1/support/me/tickets/
GET    /api/v1/support/me/tickets/{ticket_number}/
PATCH  /api/v1/support/me/tickets/{ticket_number}/
POST   /api/v1/support/me/tickets/{ticket_number}/submit/
POST   /api/v1/support/me/tickets/{ticket_number}/reply/
GET    /api/v1/support/me/tickets/{ticket_number}/timeline/
POST   /api/v1/support/me/tickets/{ticket_number}/attachments/
POST   /api/v1/support/me/tickets/{ticket_number}/reopen/
POST   /api/v1/support/me/tickets/{ticket_number}/satisfaction/
```

### Admin API summary

```text
GET/POST       /api/v1/support/admin/departments/
GET/PATCH/DELETE /api/v1/support/admin/departments/{id}/
GET/POST       /api/v1/support/admin/categories/
PATCH/DELETE   /api/v1/support/admin/categories/{id}/
GET/POST       /api/v1/support/admin/ticket-types/
PATCH          /api/v1/support/admin/ticket-types/{id}/
GET/POST       /api/v1/support/admin/sla-policies/
PATCH          /api/v1/support/admin/sla-policies/{id}/
GET/POST       /api/v1/support/admin/canned-responses/
PATCH          /api/v1/support/admin/canned-responses/{id}/
POST           /api/v1/support/admin/canned-responses/{id}/use/
GET/POST       /api/v1/support/admin/knowledge/articles/
GET/PATCH      /api/v1/support/admin/knowledge/articles/{id}/
POST           /api/v1/support/admin/knowledge/articles/{id}/publish/
POST           /api/v1/support/admin/knowledge/articles/{id}/archive/
POST           /api/v1/support/admin/knowledge/articles/{id}/use/
GET            /api/v1/support/admin/tickets/
GET            /api/v1/support/admin/tickets/{ticket_number}/
POST           /api/v1/support/admin/tickets/{ticket_number}/reply/
POST           /api/v1/support/admin/tickets/{ticket_number}/internal-note/
POST           /api/v1/support/admin/tickets/{ticket_number}/assign/
GET            /api/v1/support/admin/tickets/{ticket_number}/assignment-recommendation/
POST           /api/v1/support/admin/tickets/{ticket_number}/auto-assign/
GET            /api/v1/support/admin/tickets/{ticket_number}/smart-replies/
POST           /api/v1/support/admin/tickets/{ticket_number}/smart-replies/use/
POST           /api/v1/support/admin/tickets/{ticket_number}/status/
POST           /api/v1/support/admin/tickets/{ticket_number}/escalate/
POST           /api/v1/support/admin/tickets/{ticket_number}/close/
GET            /api/v1/support/admin/duplicates/
POST           /api/v1/support/admin/duplicates/{id}/review/
GET            /api/v1/support/admin/analytics/
GET            /api/v1/support/admin/export/tickets/
GET            /api/v1/support/admin/export/messages/
GET            /api/v1/support/admin/export/sla/
GET            /api/v1/support/admin/export/csat/
```

### Celery tasks

```text
apps.support_desk.tasks.mark_support_sla_breaches_task
apps.support_desk.tasks.cleanup_stale_support_drafts_task
apps.support_desk.tasks.daily_support_digest_task
```

---



## Apex Unified Admin Command Center

Apex B4 یک مرکز فرماندهی مرکزی برای ادمین اضافه کرده است:

```text
GET /api/v1/admin/command-center/
```

این endpoint وضعیت عملیاتی همه اپ‌های مهم را یکجا نشان می‌دهد:

```text
Support Desk: open/unassigned/SLA breached/escalated tickets
Kindness Wall: pending listings/reports/duplicates/contact reveals
Tabyin: pending user submissions/deleted-in-source contents
Public Reports: pending/reviewing/approved/rejected reports
R4J: published criminals/pending reports/active bounties
Madadkar: campaigns/payments success/failure/pending
LMS: courses/enrollments/certificates
Notifications: pending/failed events and deliveries
Activity Timeline: total/recent activities
Provider readiness: email/sms/payment
Health summary: database/cache/celery broker status
```

این فاز پروژه را از مجموعه‌ای از اپ‌های مستقل به یک platform مدیریتی قابل مانیتور و عملیات نزدیک می‌کند.

## Apex Notification Engine

Apex A2 یک notification engine مشترک اضافه کرده است:

```text
apps/notifications/
```

قابلیت‌ها:

```text
NotificationTemplate
NotificationEvent
NotificationDelivery
NotificationPreference
channel abstraction: in_app, email, sms, webhook
service-layer event creation and dispatch
Celery async dispatch task
user inbox APIs
user preferences
admin event/delivery/template inspection
provider integration with Django email and configured SMS adapter
```

API summary:

```text
GET  /api/v1/notifications/me/
POST /api/v1/notifications/me/{id}/read/
POST /api/v1/notifications/me/read-all/
GET  /api/v1/notifications/me/preferences/
POST /api/v1/notifications/me/preferences/
GET  /api/v1/notifications/admin/events/
GET  /api/v1/notifications/admin/deliveries/
GET  /api/v1/notifications/admin/templates/
```

این engine برای اتصال رویدادهای Support Desk، Kindness Wall، LMS، Madadkar، R4J، Tabyin و Auth آماده است.

## 18. Redis / Cache / Celery / Observability

### Redis

در production-like runtime:

```text
Redis DB 1 → cache
Redis DB 2 → Celery broker/result backend
```

envها:

```env
CACHE_BACKEND=redis
REDIS_URL=redis://redis:6379/1
CELERY_BROKER_URL=redis://redis:6379/2
CELERY_RESULT_BACKEND=redis://redis:6379/2
```

### Cache

- cache helpers در `apps/core/cache.py`
- namespace versioning
- selector-level cache در Tabyin public content
- invalidation بعد از sync/toggle

### Celery queues

```text
default
tabyin_sync
madadkar
```

Worker docker command:

```text
celery -A config worker --loglevel=info -Q default,tabyin_sync,madadkar
```

Beat schedule:

```text
Tabyin incremental sync every 30 min
Tabyin full sync daily
Madadkar stale participation cleanup every 5 min
Madadkar expired campaign close every 10 min
Support SLA breach detection every 5 min
Support stale draft cleanup daily
Support daily digest daily
Notification event async dispatch
```

### Structured logging

Production logging می‌تواند JSON شود:

```env
LOG_FORMAT=json
```

فرمت JSON شامل موارد زیر است:

```text
timestamp
level
logger
message
request_id
module
function
line
exception.type/message/stacktrace
```

در development مقدار پیش‌فرض خواناتر است:

```env
LOG_FORMAT=text
```

### Request ID

هر request دارای header زیر است:

```text
X-Request-ID
```

اگر client/proxy مقدار معتبر بدهد حفظ می‌شود، در غیر این صورت server مقدار جدید می‌سازد. همین مقدار وارد logها هم می‌شود.

### Prometheus metrics

Endpoint:

```text
GET /api/v1/metrics/
```

فعال/غیرفعال:

```env
PROMETHEUS_METRICS_ENABLED=True
```

Metrics فعلی:

```text
setadjang_http_requests_total
setadjang_http_request_duration_seconds
setadjang_celery_tasks_total
setadjang_celery_task_duration_seconds
```

برای کنترل cardinality، pathها normalize می‌شوند؛ مثل `{id}` و `{token}`.

### Sentry

Sentry کاملاً اختیاری و env-driven است:

```env
SENTRY_DSN=
SENTRY_TRACES_SAMPLE_RATE=0.0
SENTRY_PROFILES_SAMPLE_RATE=0.0
```

اگر DSN خالی باشد initialize نمی‌شود. `send_default_pii=False` تنظیم شده تا PII به‌صورت پیش‌فرض ارسال نشود.

### OpenTelemetry

Tracer provider اختیاری:

```env
OTEL_ENABLED=False
OTEL_SERVICE_NAME=setad-jang-api
```

Exporter wiring در deployment layer قابل اضافه شدن است بدون تغییر business code.

---

## 19. Providers: SMS / Payment / Email

### SMS

SMS provider واقعی به مجوز نیاز دارد. تا قبل از مجوز:

- provider abstraction باید باقی بماند.
- dev/test از email/console/mock استفاده می‌کند.
- بعد از مجوز، فقط env/provider credentials باید عوض شود.

هدف production readiness پس از اخذ مجوز:

```env
OTP_PROVIDER=sms
OTP_SMS_PROVIDER=http
SMS_API_URL=https://sms-provider.example/send
SMS_API_KEY=...
SMS_SENDER=...
SMS_TIMEOUT_SECONDS=10
```

Adapter عمومی HTTP آماده است و payload استاندارد `to/message/sender/purpose` ارسال می‌کند. اگر vendor نهایی schema متفاوتی بخواهد، فقط adapter جدید اضافه می‌شود؛ OTP service و business flow تغییر نمی‌کند.

Provider readiness بدون ارسال SMS واقعی قابل بررسی است و در detailed health به‌صورت diagnostic گزارش می‌شود.

### Zarinpal

Zarinpal هم به مجوز/merchant id نیاز دارد. تا قبل از مجوز:

```env
MADADKAR_PAYMENT_PROVIDER=sandbox
```

بعد از مجوز:

```env
MADADKAR_PAYMENT_PROVIDER=zarinpal
MADADKAR_ZARINPAL_MERCHANT_ID=...
MADADKAR_ZARINPAL_SANDBOX=False
```

کد provider آماده است و هدف این است که بعداً فقط env جایگزین شود.

### Email SMTP رایگان پیشنهادی

برای SMTP رایگان و transactional، پیشنهاد عملی:

```text
Brevo SMTP
```

env پیشنهادی:

```env
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp-relay.brevo.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=<brevo-login>
EMAIL_HOST_PASSWORD=<brevo-smtp-key>
DEFAULT_FROM_EMAIL=noreply@your-domain.com
```

نکته production:

- دامنه باید SPF/DKIM داشته باشد.
- از Gmail شخصی برای transactional production استفاده نشود.
- staging باید email sandbox/console داشته باشد.

---

## 20. Production Runbooks

Runbookهای production در مسیر زیر هستند:

```text
docs/production/ENVIRONMENT_MATRIX.md
docs/production/DEPLOYMENT_RUNBOOK.md
docs/production/BACKUP_RESTORE_RUNBOOK.md
docs/production/INCIDENT_RESPONSE_RUNBOOK.md
docs/production/SECRET_ROTATION_RUNBOOK.md
docs/production/RELEASE_CHECKLIST.md
docs/production/PRODUCTION_10_10_STATUS.md
```

این اسناد پوشش می‌دهند:

```text
environment matrix
deployment order
rollback
backup/restore
incident response
secret rotation
release checklist
provider go-live checklist
production 10/10 status
```

---

## 21. Production Checklist

### Security

```text
SECRET_KEY قوی
JWT_SIGNING_KEY جداگانه
DEBUG=False
ALLOWED_HOSTS دقیق
CORS محدود
pip-audit clean
Bandit clean
Detect-secrets baseline clean
GitHub tokenها rotate/revoke شده باشند
```

### Runtime

```text
PostgreSQL production
Redis persistent/managed
Gunicorn behind HTTPS reverse proxy
Celery worker + beat
Flower protected or internal-only
Docker healthcheck readiness
backup/restore policy
```

### Media / Object Storage / CDN

```text
MEDIA_STORAGE_BACKEND=local برای development
MEDIA_STORAGE_BACKEND=s3 برای production/MinIO/S3
public_media storage برای فایل‌های public و CDN-friendly
private_media storage برای فایل‌های private با signed URL
AWS_S3_CUSTOM_DOMAIN برای CDN domain
FILE_SCAN_PROVIDER=extension_blocklist به‌عنوان baseline security scanner
```

برای LMS، ویدیوها و فایل‌های حجیم نباید در production از خود Django سرو شوند. مسیر حرفه‌ای:

```text
Django metadata/permission را مدیریت می‌کند
Object Storage فایل را نگه می‌دارد
CDN فایل‌های public/heavy را تحویل می‌دهد
Private files با signed URL تحویل می‌شوند
Worker/Celery برای scan/cleanup/processing قابل استفاده است
```

### Providers

```text
Brevo SMTP یا SMTP transactional رایگان با DKIM/SPF
SMS provider بعد از مجوز
Zarinpal بعد از مجوز
Object storage برای media
Signed URLs برای فایل‌های private
```

### Observability

```text
Structured JSON logging آماده است
Sentry env-driven آماده است
OpenTelemetry tracer provider آماده است
Prometheus metrics endpoint آماده است
HTTP request latency metrics آماده است
HTTP performance contracts آماده است
Slow request telemetry و Prometheus counter آماده است
Response headers: X-Response-Time-ms و X-Performance-Budget-ms
Advanced detailed health diagnostics آماده است: migration state، media storage، audit-chain quick، performance contracts
DB query telemetry آماده است: X-DB-Query-Count، X-DB-Time-ms، slow DB query counters
Request-scoped DB query count/time budgets آماده است
Endpoint performance contract tests برای critical endpoints آماده است
API envelope contract tests برای success/error/pagination آماده است
OpenAPI contract hardening برای operationId، critical path coverage، component schemas و content-types آماده است
N+1/query-count regression guards در CI آماده است
Celery task metrics آماده است
Slow query monitoring در فاز hardening بعدی قابل تکمیل است
```

---

## 22. فلسفه مهندسی

```text
Correctness before speed
Security by default
No shortcut MVP in important domains
Service-layer mutations
Selector-layer reads
Auditability for sensitive actions
Tests as contracts
OpenAPI as contract
Zero-warning policy
Production readiness is a feature
```

هدف نهایی: backendای که نه فقط کار کند، بلکه از نظر senior/enterprise engineering قابل دفاع باشد.
