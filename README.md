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
  <img alt="Tests" src="https://img.shields.io/badge/tests-1032%2B%20passed-brightgreen?style=for-the-badge" />
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
- [18. Redis / Cache / Celery](#18-redis--cache--celery)
- [19. Providers: SMS / Payment / Email](#19-providers-sms--payment--email)
- [20. Production Checklist](#20-production-checklist)
- [21. فلسفه مهندسی](#21-فلسفه-مهندسی)

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
python -m pytest -q                              ✅ 1032+ passed
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
pytest -q
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
full pytest
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
- full pytest
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

Health checks شامل database/cache/Celery-relevant dependencies است و secret-safe طراحی شده است.

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
GET  /api/v1/auth/me/
GET/PATCH /api/v1/auth/profile/
GET  /api/v1/auth/admin/users/
GET  /api/v1/auth/admin/users/{id}/
POST /api/v1/auth/admin/users/{id}/role/
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

## 12. Audit Logs

اپ `audit_logs` برای forensic audit trail طراحی شده است.

### قابلیت‌ها

- append-oriented audit log
- action constants برای همه دامنه‌ها
- async audit dispatch via Celery
- metadata extraction:
  - IP
  - user agent
  - request id
- admin list/detail
- immutability hardening

### API summary

```text
GET /api/v1/audit-logs/admin/logs/
GET /api/v1/audit-logs/admin/logs/{id}/
```

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
```

### Celery tasks

```text
apps.madadkar.tasks.expire_stale_participations_task
apps.madadkar.tasks.close_expired_campaigns_task
```

Queue:

```text
madadkar
```

---

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
- status history
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
GET            /api/v1/support/admin/tickets/
GET            /api/v1/support/admin/tickets/{ticket_number}/
POST           /api/v1/support/admin/tickets/{ticket_number}/reply/
POST           /api/v1/support/admin/tickets/{ticket_number}/internal-note/
POST           /api/v1/support/admin/tickets/{ticket_number}/assign/
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

## 18. Redis / Cache / Celery

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
```

---

## 19. Providers: SMS / Payment / Email

### SMS

SMS provider واقعی به مجوز نیاز دارد. تا قبل از مجوز:

- provider abstraction باید باقی بماند.
- dev/test از email/console/mock استفاده می‌کند.
- بعد از مجوز، فقط env/provider credentials باید عوض شود.

هدف production readiness:

```text
OTP_PROVIDER=sms
SMS_PROVIDER=<licensed-provider>
SMS_API_KEY=...
```

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

## 20. Production Checklist

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

### Providers

```text
Brevo SMTP یا SMTP transactional رایگان با DKIM/SPF
SMS provider بعد از مجوز
Zarinpal بعد از مجوز
Object storage برای media
Signed URLs برای فایل‌های private
```

### Observability آینده

```text
Sentry
OpenTelemetry
Prometheus metrics
Structured JSON logging
Slow query monitoring
Celery task metrics
```

---

## 21. فلسفه مهندسی

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
