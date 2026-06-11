# ستاد جنگ — Setad Jang Enterprise Backend

<p align="center">
  <strong>Enterprise-grade Django REST Framework backend</strong><br />
  Django 6 · DRF · Celery · Redis · PostgreSQL · OpenAPI · JWT · Audit Logs · Payment Ledger
</p>

<p align="center">
  <img alt="Django" src="https://img.shields.io/badge/Django-6.x-0C4B33?style=for-the-badge&logo=django&logoColor=white" />
  <img alt="DRF" src="https://img.shields.io/badge/DRF-3.x-A30000?style=for-the-badge" />
  <img alt="Celery" src="https://img.shields.io/badge/Celery-5.x-37814A?style=for-the-badge&logo=celery&logoColor=white" />
  <img alt="PostgreSQL" src="https://img.shields.io/badge/PostgreSQL-Production-4169E1?style=for-the-badge&logo=postgresql&logoColor=white" />
  <img alt="Tests" src="https://img.shields.io/badge/tests-928%2B%20passed-brightgreen?style=for-the-badge" />
</p>

---

## 1. پروژه چیست؟

**Setad Jang** یک backend بزرگ، چنددامنه‌ای و production-minded است که با هدف نمایش توانمندی معماری backend در سطح enterprise ساخته شده است.

تمرکز پروژه فقط «کار کردن API» نیست؛ هدف این است که هر بخش از سیستم از نظر معماری، امنیت، تست، observability، auditability، performance و developer experience قابل دفاع باشد.

این پروژه شامل چند اپ مستقل اما هماهنگ است:

- احراز هویت چندشناسه‌ای با OTP امن
- گزارشات مردمی
- موتور sync محتوای تبیین
- Audit logs forensic-grade
- R4J / Reward for Justice
- مددکار / charitable crowdfunding با payment gateway و ledger مالی
- health/readiness/observability production-grade
- CI/CD quality gates

---

## 2. وضعیت فعلی کیفیت پروژه

Quality gate فعلی پروژه:

```bash
make verify
```

خروجی آخرین verification:

```text
pip check                                      ✅ No broken requirements
ruff check .                                  ✅ All checks passed
python manage.py check                        ✅ No issues
python manage.py check --deploy               ✅ No issues
python manage.py makemigrations --check       ✅ No changes detected
python manage.py spectacular --validate       ✅ Clean OpenAPI schema
pytest -q                                     ✅ 928+ passed
```

پروژه با policy زیر نگهداری می‌شود:

```text
Zero-warning policy
No placeholder / TODO / pass in production code
No direct DB mutation in views
Service layer for mutations
Selector layer for reads
Audit logging for sensitive operations
Schema validation after changes
Full regression before major push
```

---

## 3. معماری کلان

```text
Client / Frontend
      │
      ▼
Django REST Framework API
      │
      ├── Views              → orchestration only, no business logic
      ├── Serializers        → input/output contract + validation
      ├── Services           → mutations, transactions, state machines
      ├── Selectors          → read-side queries, prefetch/select_related, cache-aware reads
      ├── Permissions        → role / ownership / verification boundaries
      ├── Throttles          → abuse protection
      ├── Audit Logs         → async/sync forensic activity trail
      ├── Celery Tasks       → async sync, maintenance, audit dispatch
      └── OpenAPI Schema     → drf-spectacular documentation

PostgreSQL                  → production database
Redis                       → cache + Celery broker + anomaly guard
Celery Worker/Beat          → async/background workflows
Docker Compose              → web + postgres + redis + worker + beat + flower
GitHub Actions              → automated quality gate
```

اصل مهم پروژه:

> View فقط مرز HTTP است. منطق واقعی در service/selector layer قرار دارد.

---

## 4. اپ‌ها و قابلیت‌ها

### 4.1 Core

زیرساخت مشترک پروژه:

- `BaseModel` با `created_at`, `updated_at`, `is_active`
- soft delete managerها
- response envelope یکپارچه
- pagination envelope-aware
- custom exception handler
- request ID middleware
- health/liveness/readiness/detailed endpoints
- cache helpers با namespace versioning
- schema helperهای OpenAPI

Response envelope استاندارد:

```json
{
  "success": true,
  "status_code": 200,
  "message": "عملیات با موفقیت انجام شد.",
  "data": {}
}
```

Error envelope:

```json
{
  "success": false,
  "status_code": 400,
  "message": "درخواست نامعتبر است.",
  "errors": {}
}
```

---

### 4.2 Authentication

سیستم احراز هویت چندشناسه‌ای:

- ثبت‌نام با ایمیل یا شماره موبایل
- login با password یا OTP
- JWT access/refresh با rotation و blacklist
- custom user model
- profile تکمیلی
- primary identifier switching
- اتصال identifier دوم
- legacy auth endpoint deprecation

امنیت OTP:

- OTP plain در DB ذخیره نمی‌شود
- hash با HMAC/SHA-256
- replay protection
- race-safe conditional update
- attempt limit با DB-side `F()` expression
- cooldown per identifier/purpose
- provider pattern برای email/SMS
- honeypot anti-bot
- global OTP anomaly guard
- identifier masking در logs برای جلوگیری از PII leakage

---

### 4.3 Public Reports

گزارشات مردمی:

- subjectهای قابل مدیریت توسط ادمین
- ثبت گزارش عمومی با attachment
- audit برای create/update/delete/status change
- state machine وضعیت گزارش
- privacy-safe public response
- upload validation
- admin filters و pagination
- operational indexes

State machine گزارش:

```text
PENDING   → REVIEWING / APPROVED / REJECTED
REVIEWING → PENDING / APPROVED / REJECTED
APPROVED  → terminal
REJECTED  → terminal
```

---

### 4.4 Tabyin

موتور محتوای جهاد تبیین:

- sync کامل و افزایشی از منبع خارجی Armansky/Mohtavanegar
- provider pattern
- HTTP retry/backoff
- hashing برای change detection
- bulk DB operations
- soft delete برای محتوای حذف‌شده در منبع
- Celery scheduled sync
- cache-aware public selectors
- admin toggle
- async sync dispatch + task status endpoint

قابلیت جدید:

- کاربران لاگین‌شده می‌توانند محتوا به بانک تبیین اضافه کنند
- محتوای کاربر ابتدا `pending review` می‌شود
- ادمین approve/reject می‌کند
- فقط بعد از approve در public API نمایش داده می‌شود
- محتوای کرول‌شده همچنان auto-approved است و نیاز به review ندارد
- owner-based submission list/detail
- audit actions برای submit/approve/reject

---

### 4.5 Audit Logs

Audit trail پروژه forensic-grade شده است:

- append-only در سطح model و queryset
- جلوگیری از update/delete/soft-delete/restore
- sync audit برای عملیات compliance-critical
- async audit برای عملیات latency-sensitive
- metadata کامل:
  - user
  - action
  - resource type/id
  - IP
  - request ID
  - user-agent
  - path
  - method
  - changes
  - extra data

Audit API فقط admin و read-only است.

---

### 4.6 R4J — Reward for Justice

دامنه R4J شامل:

- criminal profile
- aliases
- phones
- socials
- photos
- attachments
- field visibility
- community reports
- per-field review
- bounties
- cancel request flows

ویژگی‌های معماری:

- field applicator registry
- visibility map برای public fields
- state machine گزارش و bounty
- counter sync برای bounty totals
- concurrency-safe bounty operations
- IDOR protection
- query performance contracts
- operational indexes

---

### 4.7 Madadkar — Charitable Crowdfunding

اپ مددکار یک سیستم crowdfunding سهم‌محور است:

- Sponsor
- Campaign
- Campaign gallery
- Participation
- Payment
- PaymentEvent ledger
- analytics
- Excel export
- maintenance tasks

Payment architecture:

- provider pattern
- SandboxProvider
- ZarinpalProvider واقعی با HTTP integration
- idempotent verify
- anti-tampering amount check
- share reservation با `select_for_update`
- stale participation expiration
- auto-complete campaign
- append-only payment event ledger

Payment ledger:

```text
CREATED
VERIFY_SUCCESS
VERIFY_FAILED
AMOUNT_MISMATCH
EXPIRED
```

این ledger مسیر تغییرات مالی را ثبت می‌کند؛ `Payment` فقط آخرین وضعیت را نگه می‌دارد.

---

## 5. Observability و Health

سه سطح health داریم:

```text
GET /api/v1/health/           → liveness
GET /api/v1/health/ready/     → readiness
GET /api/v1/health/detailed/  → detailed diagnostics
```

### Liveness

Dependency خارجی را لمس نمی‌کند و فقط زنده بودن process را نشان می‌دهد.

### Readiness

Dependencyهای critical را چک می‌کند:

- database
- cache
- Celery broker

### Detailed

Readiness + diagnosticهای تکمیلی:

- Tabyin sync stats
- system info
- version
- environment
- uptime

Health responseها secret-safe هستند و credential/traceback خام leak نمی‌کنند.

---

## 6. Logging

Logging پروژه traceable و request-aware است:

```text
{asctime} [{levelname}] [{request_id}] {name}: {message}
```

قواعد مهم:

- هر request یک request_id دارد
- لاگ‌های حساس PII کامل را ذخیره نمی‌کنند
- auth identifiers mask می‌شوند
- OTP/token/password در audit/log ذخیره نمی‌شود
- health degraded/error component-level logging دارد
- payment mismatch با error-level ثبت می‌شود
- audit metadata برای incident review ذخیره می‌شود

---

## 7. Celery و Background Jobs

Celery برای taskهای async و scheduled استفاده می‌شود:

```text
tabyin sync incremental
 tabyin sync full
 audit log async write
 madadkar stale participation expiration
 madadkar expired campaign close
```

Queueها:

```text
default
tabyin_sync
madadkar
```

Docker worker همه queueهای لازم را consume می‌کند.

---

## 8. Docker Compose

سرویس‌ها:

```text
web       → Django/Gunicorn
postgres  → PostgreSQL
redis     → cache + broker
worker    → Celery worker
beat      → Celery beat
flower    → Celery monitoring
```

Healthcheck کانتینر web روی readiness endpoint است:

```text
/api/v1/health/ready/
```

---

## 9. نصب و اجرای local

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
make install
python manage.py migrate
python manage.py runserver
```

یا بدون Makefile:

```bash
pip install -r requirements.txt -r requirements-dev.txt
python manage.py migrate
python manage.py runserver
```

---

## 10. اجرای Docker

`.env.example` را به `.env` کپی کن و مقدارهای حساس را تغییر بده:

```env
SECRET_KEY=<strong-secret-key>
POSTGRES_PASSWORD=<strong-postgres-password>
```

سپس:

```bash
docker-compose up --build -d
docker-compose exec web python manage.py migrate
docker-compose exec web python manage.py collectstatic --noinput
docker-compose exec web pytest -q
```

---

## 11. Quality Gate و Developer Commands

تمام commandهای اصلی در Makefile متمرکز شده‌اند:

```bash
make install
make lint
make check
make deploy-check
make migrations-check
make schema-check
make schema-update
make pip-check
make test
make verify-fast
make verify
```

مهم‌ترین دستور:

```bash
make verify
```

که اجرا می‌کند:

```text
pip check
ruff check .
python manage.py check
python manage.py check --deploy
python manage.py makemigrations --check --dry-run
python manage.py spectacular --validate
pytest -q
```

---

## 12. CI/CD

GitHub Actions quality gate اضافه شده است:

```text
.github/workflows/ci.yml
```

CI شامل:

- PostgreSQL service container
- Redis service container
- Python 3.14
- pip cache
- dependency install
- pip check
- Ruff
- Django check
- deployment check
- migration drift check
- OpenAPI schema validation
- full pytest
- schema artifact upload

---

## 13. OpenAPI Documentation

بعد از اجرای سرور:

```text
Swagger UI : /api/docs/
ReDoc      : /api/redoc/
Schema     : /api/schema/
```

Schema committed:

```text
schema.yaml
```

برای regenerate:

```bash
make schema-update
```

---

## 14. Production Checklist

قبل از production واقعی:

```text
SECRET_KEY قوی و غیرپیش‌فرض
JWT_SIGNING_KEY جداگانه
DEBUG=False
ALLOWED_HOSTS دقیق
PostgreSQL با backup policy
Redis پایدار
HTTPS پشت reverse proxy
CORS محدود
worker queueها: default,tabyin_sync,madadkar
Celery beat فعال
monitoring برای logs/health/flower
Zarinpal merchant id واقعی
MADADKAR_PAYMENT_PROVIDER=zarinpal
```

---

## 15. ساختار پروژه

```text
apps/
  core/
  authentication/
  public_reports/
  tabyin/
  audit_logs/
  r4j/
  madadkar/
config/
  settings/
  celery.py
  urls.py
tests/
  factories/
docs/
  PROJECT_EXCELLENCE_PLAN.md
```

جزئیات کامل‌تر در:

```text
STRUCTURE.md
```

---

## 16. فلسفه مهندسی پروژه

این پروژه بر اساس چند اصل ساخته شده است:

```text
Correctness before speed
Security by default
Observability by design
Service-layer mutations
Selector-layer reads
Tests as contracts
No silent failure in critical paths
No warning tolerated
No placeholder in production code
```

هدف نهایی: backendای که نه فقط کار کند، بلکه از نظر senior engineering قابل دفاع باشد.
