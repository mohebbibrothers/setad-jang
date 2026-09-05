# ستاد جنگ — Setad Jang Enterprise Platform

<p align="center">
  <strong>Backend/Platform چنددامنه‌ای، API-first، production-minded و قابل دفاع در سطح enterprise</strong><br />
  Django 6 · DRF · PostgreSQL · Redis · Celery · OpenAPI · JWT · Audit Trail · Observability · Financial Workflows · Case Management
</p>

<p align="center">
  <img alt="Django" src="https://img.shields.io/badge/Django-6.x-0C4B33?style=for-the-badge&logo=django&logoColor=white" />
  <img alt="DRF" src="https://img.shields.io/badge/DRF-3.x-A30000?style=for-the-badge" />
  <img alt="PostgreSQL" src="https://img.shields.io/badge/PostgreSQL-production-4169E1?style=for-the-badge&logo=postgresql&logoColor=white" />
  <img alt="Redis" src="https://img.shields.io/badge/Redis-cache%20%2B%20broker-DC382D?style=for-the-badge&logo=redis&logoColor=white" />
  <img alt="Celery" src="https://img.shields.io/badge/Celery-worker%20%2B%20beat-37814A?style=for-the-badge&logo=celery&logoColor=white" />
  <img alt="Tests" src="https://img.shields.io/badge/tests-1451%20passed-brightgreen?style=for-the-badge" />
  <img alt="Security" src="https://img.shields.io/badge/security-pip--audit%20%2B%20bandit%20%2B%20detect--secrets-blue?style=for-the-badge" />
</p>

---

## 0. فهرست انتخاب سریع

### شروع سریع و عملیات روزانه

- [1. معرفی پروژه و فلسفه طراحی](#1-معرفی-پروژه-و-فلسفه-طراحی)
- [2. وضعیت کیفیت، تست و امنیت](#2-وضعیت-کیفیت-تست-و-امنیت)
- [3. نصب و اجرای Local](#3-نصب-و-اجرای-local)
- [4. Docker، Runtime و Orchestration محلی](#4-docker-runtime-و-orchestration-محلی)
- [5. Makefile، CI و Quality Gates](#5-makefile-ci-و-quality-gates)
- [6. OpenAPI، Swagger و قرارداد API](#6-openapi-swagger-و-قرارداد-api)
- [6.1. راهنمای اتصال Frontend](#61-راهنمای-اتصال-frontend)
- [7. تنظیمات Environment و Providerها](#7-تنظیمات-environment-و-providerها)

### معماری و زیرساخت مشترک

- [8. معماری کلان و قراردادهای کدنویسی](#8-معماری-کلان-و-قراردادهای-کدنویسی)
- [9. Core Infrastructure](#9-core-infrastructure)
- [10. Audit Logs و Forensics](#10-audit-logs-و-forensics)
- [11. Notification Engine](#11-notification-engine)
- [12. Activity Timeline](#12-activity-timeline)
- [13. Unified Admin Command Center](#13-unified-admin-command-center)

### اپ‌های دامنه‌ای

- [14. Authentication و Identity](#14-authentication-و-identity)
- [15. Public Reports](#15-public-reports)
- [16. Tabyin](#16-tabyin)
- [17. R4J — Reward for Justice](#17-r4j--reward-for-justice)
- [18. Madadkar — Charitable Crowdfunding](#18-madadkar--charitable-crowdfunding)
- [19. LMS — Learning Management System](#19-lms--learning-management-system)
- [20. Kindness Wall — Divar-e Mehrabani](#20-kindness-wall--divar-e-mehrabani)
- [21. Support Desk](#21-support-desk)

### عملیات، دیپلوی، نگه‌داری

- [22. Celery، Redis، Cache و Job Scheduling](#22-celery-redis-cache-و-job-scheduling)
- [23. Media، Object Storage و CDN Readiness](#23-media-object-storage-و-cdn-readiness)
- [24. Observability، Health و Metrics](#24-observability-health-و-metrics)
- [25. سناریوهای عملیاتی انتها به انتها](#25-سناریوهای-عملیاتی-انتها-به-انتها)
- [26. Production Runbooks](#26-production-runbooks)
- [27. چک‌لیست Production](#27-چکلیست-production)
- [28. نقشه فایل‌ها و مسئولیت هر بخش](#28-نقشه-فایلها-و-مسئولیت-هر-بخش)

---

## 1. معرفی پروژه و فلسفه طراحی

**Setad Jang** یک پروژه تک‌اپلیکیشنی ساده نیست؛ یک platform چنددامنه‌ای است که چندین دامنه عملیاتی را زیر یک backend منسجم جمع کرده است:

```text
Identity / Auth
Public Reports
Tabyin Content Sync
R4J Criminal Profiles + Evidence + Investigation Cases
Madadkar Financial Crowdfunding
LMS Learning Platform
Kindness Wall Matching Platform
Support Desk Ticketing
Notifications
Activity Timeline
Audit / Forensics
Command Center
Core Observability / Health / Performance
```

هدف اصلی پروژه:

```text
ساخت یک backend قابل اجرا، قابل تست، قابل audit، قابل توسعه و قابل دفاع در سطح production.
```

اصل معماری کلیدی:

> View فقط مرز HTTP و orchestration است؛ mutation باید در service layer و read مهم باید در selector layer انجام شود.

این یعنی:

- APIها thin هستند.
- business logic در view پخش نشده است.
- mutationها transaction-safe هستند.
- readها قابل optimize و test هستند.
- audit و side-effectها در نقاط مشخص کنترل می‌شوند.
- OpenAPI قرارداد رسمی API است.

---

## 2. وضعیت کیفیت، تست و امنیت

آخرین gate کامل پروژه:

```bash
make verify
```

وضعیت آخرین verification موفق:

```text
pip check                         ✅ No broken requirements
lock check                        ✅ lockfiles هم‌ارز با requirements‌ها
pip-audit                         ✅ No known vulnerabilities
bandit                            ✅ Production SAST gate clean
detect-secrets                    ✅ Baseline-controlled secret scan
ruff lint + format-check          ✅ All checks passed
type gate (mypy)                  ✅ Success: no issues found in 343 source files
django check                      ✅ No issues
django deploy check               ✅ No issues
makemigrations --check            ✅ No changes detected
OpenAPI validation                ✅ Valid schema
STRUCTURE.md check                ✅ همگام با درخت واقعی مخزن
compose config (CI)               ✅ interpolate/`:?` زنده در هر push
nginx config test (CI)            ✅ nginx -t روی deploy/nginx.conf
pytest + coverage gate            ✅ 1886 passed / 25 skipped (راتچت: جدول با collect سوئیت می‌خواند)
coverage                          ✅ 85.85% >= 82%
```

Policyهای مهندسی enforced:

```text
Zero-warning policy
No placeholder/TODO/pass in production code
No direct DB mutation in views
No migration drift
No OpenAPI warning
No security gate bypass
Sensitive mutations must be audit logged
```

نکته مهم: اگر اجرای `make verify` روی محیط تازه با خطای `No module named ...` شکست، دلیل آن نصب نبودن dependencyهای محیط است، نه خرابی پروژه. ابتدا اجرا کن:

```bash
python -m pip install -r requirements.txt -r requirements-dev.txt
```

---

## 3. نصب و اجرای Local

### 3.1 پیش‌نیازها

```text
Python 3.14 برای CI/Docker هدف‌گذاری شده است.
PostgreSQL برای production-like runtime توصیه می‌شود.
Redis برای cache/Celery لازم است.
```

### 3.2 نصب استاندارد با virtualenv

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
make install
python manage.py migrate
python manage.py runserver
```

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
make install
python manage.py migrate
python manage.py runserver
```

### 3.3 ساخت superuser

```bash
python manage.py createsuperuser
```

### 3.4 اجرای تست‌ها

```bash
make test
make coverage
make verify
```

### 3.5 regenerate کردن schema

```bash
make schema-update
```

فایل تولیدی:

```text
schema.yaml
```

---

## 4. Docker، Runtime و Orchestration محلی

### 4.1 سرویس‌ها

`docker-compose.yml` یک runtime production-like محلی می‌سازد:

```text
web       → Django/Gunicorn
postgres  → PostgreSQL 17
redis     → Redis cache/broker/result backend
worker    → Celery worker
beat      → Celery beat scheduler
flower    → Celery monitoring UI
```

### 4.2 اجرا

ابتدا فایل `.env` بساز:

```bash
cp .env.example .env
```

حداقل مقدار لازم:

```env
SECRET_KEY=یک-کلید-بلند-و-تصادفی
POSTGRES_PASSWORD=یک-password-قوی
ALLOWED_HOSTS=127.0.0.1,localhost
```

اجرا:

```bash
docker-compose up --build -d
```

مشاهده لاگ:

```bash
docker-compose logs -f web
docker-compose logs -f worker
docker-compose logs -f beat
```

خاموش کردن:

```bash
docker-compose down
```

حذف volumeها فقط وقتی مطمئنی داده local مهم نیست:

```bash
docker-compose down -v
```

### 4.3 Dockerfile

Dockerfile فعلی:

- multi-stage است.
- wheelها در stage جدا ساخته می‌شوند.
- runtime کوچک‌تر و تمیزتر است.
- `tini` برای signal handling دارد.
- `gosu` برای privilege drop دارد.
- container ابتدا root است تا volume ownership را درست کند، سپس به user غیر-root drop می‌شود.
- healthcheck روی readiness است:

```text
/api/v1/health/ready/
```

### 4.4 entrypoint

`entrypoint.sh` مسئول این موارد است:

```text
ساخت/اصلاح runtime directories
wait-for Redis در صورت نیاز
اجرای migration اختیاری با RUN_MIGRATIONS=1
اجرای collectstatic اختیاری با RUN_COLLECTSTATIC=1
drop privilege به app user
اجرای command نهایی
```

---

## 5. Makefile، CI و Quality Gates

### 5.1 دستورات اصلی Makefile

```bash
make install           # نصب requirements اصلی و dev
make lint              # ruff
make check             # django check
make deploy-check      # django deployment check با env امن
make migrations-check  # کنترل migration drift
make schema-check      # validate schema در /tmp
make schema-update     # regenerate schema.yaml
make test              # pytest
make coverage          # pytest + coverage threshold
make security          # pip-audit + bandit + detect-secrets
make verify            # کل gate production
make docker-up         # docker-compose up --build -d
make docker-down       # docker-compose down
```

### 5.2 CI

`.github/workflows/ci.yml` روی push/PR به `main` اجرا می‌شود و شامل:

```text
PostgreSQL service
Redis service
Python setup
Dependency install
pip check
security gate
ruff
Django check
Django deploy check
migration drift check
OpenAPI validation
pytest coverage gate
schema artifact upload
```

### 5.3 فلسفه CI

CI فقط تست واحد نیست؛ CI قرارداد production است. اگر هرکدام از این‌ها شکست بخورد، یعنی پروژه آماده merge/push نیست:

```text
dependency graph
known vulnerabilities
static security scan
secret scan
style/lint
Django config health
production deploy warnings
migration drift
OpenAPI contract
test + coverage
```

---

## 6. OpenAPI، Swagger و قرارداد API

مسیرها:

```text
/api/schema/    → raw OpenAPI schema
/api/docs/      → Swagger UI
/api/redoc/     → ReDoc
schema.yaml     → schema commit شده و قابل کنترل در CI
```

قواعد:

- هر endpoint جدید باید schema-friendly باشد.
- response envelope باید یکپارچه بماند.
- warningهای drf-spectacular قابل قبول نیستند.
- enum collision باید با `ENUM_NAME_OVERRIDES` حل شود.
- schema باید بعد از تغییر endpoint/serializer regenerate شود:

```bash
make schema-update
```

### 6.1. راهنمای اتصال Frontend

برای اینکه frontend developer بدون حدس‌زدن بتواند از Swagger، JWT، response envelope، pagination، upload و endpointهای اصلی استفاده کند، یک سند اختصاصی اضافه شده است:

```text
docs/FRONTEND_INTEGRATION_GUIDE.md
```

مسیرهای مهم برای اتصال frontend:

```text
/api/docs/      → Swagger UI
/api/redoc/     → ReDoc
/api/schema/    → OpenAPI schema
/api/v1/health/ready/ → readiness check
```

قبل از اتصال frontend روی دامنه واقعی، حتماً envهای زیر با دامنه frontend هماهنگ شوند:

```env
ALLOWED_HOSTS=api.example.com
CORS_ALLOWED_ORIGINS=https://example.com,https://www.example.com
CSRF_TRUSTED_ORIGINS=https://example.com,https://www.example.com
```

---

## 7. تنظیمات Environment و Providerها

فایل مرجع:

```text
.env.example
```

### 7.1 Django / Security

```env
DJANGO_SETTINGS_MODULE=config.settings.production
SECRET_KEY=...
DEBUG=False
ALLOWED_HOSTS=example.com,www.example.com
CORS_ALLOWED_ORIGINS=https://example.com
CSRF_TRUSTED_ORIGINS=https://example.com
```

### 7.2 Database

برای production واقعی:

```env
DATABASE_ENGINE=postgres
POSTGRES_DB=setadjang
POSTGRES_USER=setadjang
POSTGRES_PASSWORD=strong-password
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
```

SQLite فقط برای development ساده مناسب است.

### 7.3 Redis / Celery

```env
CACHE_BACKEND=redis
REDIS_URL=redis://redis:6379/1
CELERY_BROKER_URL=redis://redis:6379/2
CELERY_RESULT_BACKEND=redis://redis:6379/2
```

### 7.4 Email SMTP

پروژه provider-ready است. پیش‌فرض توسعه console-readable است، اما برای SMTP واقعی می‌توان از Brevo SMTP رایگان/transactional استفاده کرد:

```env
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp-relay.brevo.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=...
EMAIL_HOST_PASSWORD=...
DEFAULT_FROM_EMAIL=no-reply@example.com
```

هیچ credential واقعی نباید commit شود.

### 7.5 SMS Provider

تا قبل از گرفتن مجوز SMS، provider می‌تواند dev/console بماند. کدها provider-ready هستند تا بعد از گرفتن مجوز با تغییر env فعال شوند:

```env
OTP_PROVIDER=sms
OTP_SMS_PROVIDER=http
OTP_SMS_ENDPOINT=https://provider.example/api/send
OTP_SMS_API_KEY=...
```

### 7.6 Payment Provider / Zarinpal Readiness

Madadkar از provider contract استفاده می‌کند. تا قبل از مجوز رسمی، sandbox/dev provider قابل استفاده است. بعد از دریافت مجوز، جایگزینی باید از طریق تنظیم env و provider implementation انجام شود، نه تغییر workflow مالی.

```env
MADADKAR_PAYMENT_PROVIDER=sandbox
MADADKAR_PAYMENT_CALLBACK_URL=https://example.com/api/v1/madadkar/payment/verify/
```

### 7.7 Media / Object Storage

```env
MEDIA_STORAGE_BACKEND=local
# یا:
MEDIA_STORAGE_BACKEND=s3
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_STORAGE_BUCKET_NAME=...
AWS_S3_ENDPOINT_URL=...
MEDIA_CDN_DOMAIN=cdn.example.com
```

---

## 8. معماری کلان و قراردادهای کدنویسی

### 8.1 جریان استاندارد یک request

```text
Client
  ↓
DRF View/APIView
  ↓
Serializer validation
  ↓
Service برای mutation یا Selector برای read
  ↓
Model/DB/Cache/Celery/Audit
  ↓
Response envelope
```

### 8.2 نقش فایل‌ها در هر app

```text
models.py       → state/domain persistence
choices.py      → enumهای دامنه
validators.py   → validationهای reusable
serializers.py  → input/output contract
services.py     → mutation، workflow، transaction، side-effect
selectors.py    → query/read optimization
filters.py      → query params
permissions.py  → authorization
throttles.py    → rate/abuse boundaries
views.py        → HTTP orchestration only
urls.py         → route contract
admin.py        → Django admin visibility
apps.py         → app config
migrations/     → DB schema history
tests/          → scenario + edge + contract tests
```

### 8.3 ممنوعیت‌های مهم

```text
mutation مستقیم در view ممنوع است
business rule داخل serializer سنگین ممنوع است
queryهای پیچیده و تکراری خارج از selector ممنوع است
حذف audit برای عملیات حساس ممنوع است
تغییر schema بدون schema-update ممنوع است
migration دستی بدون makemigrations/check ممنوع است
```

---

## 9. Core Infrastructure

اپ `core` زیرساخت مشترک پروژه است.

### 9.1 BaseModel

اکثر مدل‌ها از `BaseModel` استفاده می‌کنند:

```text
id
created_at
updated_at
is_active
soft_delete behavior
```

### 9.2 Response Envelope

فرمت پاسخ‌ها استاندارد است:

```json
{
  "success": true,
  "status_code": 200,
  "message": "عملیات با موفقیت انجام شد.",
  "data": {}
}
```

خطا:

```json
{
  "success": false,
  "status_code": 400,
  "message": "ورودی نامعتبر است.",
  "errors": {}
}
```

### 9.3 Health Checks

Endpointها:

```text
GET /api/v1/health/
GET /api/v1/health/ready/
GET /api/v1/health/detailed/
```

`detailed` فقط یک ping ساده نیست؛ وضعیت‌های زیر را هم پوشش می‌دهد:

```text
database
cache
migration_state
media_storage
audit_chain_quick
performance_contracts
tabyin_sync
provider_readiness
```

### 9.4 Performance Contracts

فایل‌ها:

```text
apps/core/performance.py
apps/core/performance_contracts.py
apps/core/db_performance.py
apps/core/middleware.py
apps/core/metrics.py
```

هدرهای runtime:

```text
X-Response-Time-ms
X-Performance-Budget-ms
X-DB-Query-Count
X-DB-Time-ms
```

metrics:

```text
setadjang_http_slow_requests_total
setadjang_http_db_query_count
setadjang_http_db_query_time_seconds
setadjang_http_db_slow_queries_total
```

### 9.5 Cross-App Quality Contracts

تست‌های معماری enforce می‌کنند:

```text
module docstrings
top-level class/function docstrings
عدم وجود placeholder markers
عدم mutation مستقیم در views
OpenAPI contract
API envelope contract
critical endpoint performance budget
```

---

## 10. Audit Logs و Forensics

اپ `audit_logs` ستون فقرات forensic پروژه است.

### 10.1 هدف

هر عملیات حساس باید قابل پاسخ دادن به این سؤال‌ها باشد:

```text
چه کسی؟
چه زمانی؟
از کجا؟
روی چه resource؟
چه عملیاتی؟
چه تغییری؟
با چه request_id؟
```

### 10.2 مدل AuditLog

اطلاعات کلیدی:

```text
user
action
resource_type
resource_id
ip_address
user_agent
path
method
request_id
changes
extra_data
hash chain fields
created_at
```

### 10.3 Tamper-Evident Hash Chain

برای جلوگیری از دستکاری بی‌صدا، audit chain دارای hash continuity است. اگر یک log تغییر کند یا حذف شود، verification chain آن را نشان می‌دهد.

دستور بررسی:

```bash
python manage.py verify_audit_chain
```

### 10.4 Export Forensic Package

برای incident response یا legal hold:

```bash
python manage.py export_audit_package --output ./audit_exports
```

Endpoint ادمین:

```text
GET /api/v1/audit-logs/admin/logs/export/
```

### 10.5 Retention Report

```bash
python manage.py audit_retention_report
```

نکته production: حذف خودکار audit logs عمداً aggressive نیست. طراحی فعلی archive-first است تا در forensic review داده از بین نرود.

### 10.6 APIها

```text
GET /api/v1/audit-logs/admin/logs/
GET /api/v1/audit-logs/admin/logs/{audit_log_id}/
GET /api/v1/audit-logs/admin/logs/export/
```

---

## 11. Notification Engine

اپ `notifications` موتور notification داخلی است.

### 11.1 هدف

به جای اینکه هر app مستقیم پیام بسازد، eventها و templateها در یک موتور مرکزی مدیریت می‌شوند:

```text
Domain event → Notification template → Delivery → User notification center
```

### 11.2 مفاهیم

```text
NotificationTemplate  → قالب قابل مدیریت
NotificationEvent     → رخداد دامنه‌ای
NotificationDelivery  → ارسال/نمایش برای کاربر
NotificationPreference → preference کاربر
```

### 11.3 سناریو

مثلاً در Support Desk وقتی ticket reply می‌خورد:

```text
service mutation انجام می‌شود
activity/audit ثبت می‌شود
notification event dispatch می‌شود
delivery برای user ساخته می‌شود
کاربر در /notifications/me آن را می‌بیند
```

### 11.4 APIها

```text
GET  /api/v1/notifications/me/
POST /api/v1/notifications/me/{delivery_id}/read/
POST /api/v1/notifications/me/read-all/
GET,POST /api/v1/notifications/me/preferences/
GET /api/v1/notifications/admin/events/
GET /api/v1/notifications/admin/deliveries/
GET /api/v1/notifications/admin/templates/
```

---

## 12. Activity Timeline

اپ `activity` timeline واحد برای فعالیت‌های کاربر و ادمین است.

### 12.1 هدف

Audit برای forensic است، Activity برای UX و مشاهده تاریخچه عملیاتی است. هر دو مهم‌اند اما کاربردشان متفاوت است.

```text
AuditLog  → امنیت/ردیابی/حقوقی
Activity  → timeline کاربردی/محصولی
```

### 12.2 APIها

```text
GET /api/v1/activity/me/
GET /api/v1/activity/admin/
```

### 12.3 سناریو

وقتی کاربر:

```text
ثبت‌نام می‌کند
در LMS ثبت‌نام می‌کند
در Madadkar مشارکت می‌کند
ticket می‌سازد
در Kindness Wall listing ثبت می‌کند
```

می‌توان این رویدادها را در timeline او نمایش داد.

---

## 13. Unified Admin Command Center

اپ `command_center` نمای مدیریتی یکپارچه است.

### 13.1 هدف

ادمین نباید برای فهم سلامت عملیاتی سیستم بین ۱۰ صفحه پراکنده بچرخد. Command Center snapshot خلاصه از وضعیت دامنه‌ها می‌دهد:

```text
کاربران
گزارش‌ها
R4J reports/evidence/bounties
Madadkar finance
Support queue
LMS activity
Kindness Wall moderation
Tabyin sync
provider readiness
```

### 13.2 API

```text
GET /api/v1/admin/command-center/
```

### 13.3 منطق

این endpoint read-only است و باید از selectorهای appها استفاده کند. هدف آن mutation نیست؛ هدف command visibility است.

---

## 14. Authentication و Identity

اپ `authentication` مسئول identity، OTP، login، profile، session و risk است.

### 14.1 قابلیت‌ها

```text
ثبت‌نام چندمرحله‌ای
OTP email/SMS-ready
login با password
login با OTP
JWT access/refresh
profile/me endpoints
مدیریت identifierها
password reset/change
admin user management
device/session management
risk-based authentication
risk signal review
legacy endpoint deprecation headers
anti-abuse global OTP guard
```

### 14.2 مدل‌ها و منطق

```text
User
UserIdentifier
OTPChallenge
AuthSession
AuthRiskSignal
```

- `UserIdentifier` اجازه می‌دهد email/phone و primary identifier مدیریت شود.
- `OTPChallenge` برای ثبت و کنترل lifecycle OTP است.
- `AuthSession` session/device-level visibility می‌دهد.
- `AuthRiskSignal` رخدادهایی مثل IP/device anomaly را قابل review می‌کند.

### 14.3 سناریوی ثبت‌نام OTP

```text
POST /signup/request
  → identifier normalize می‌شود
  → anti-abuse guard چک می‌شود
  → OTPChallenge ساخته می‌شود
  → provider email/sms ارسال می‌کند

POST /signup/verify
  → OTP verify می‌شود
  → user ساخته یا فعال می‌شود
  → identifier verified می‌شود
  → JWT صادر می‌شود
  → audit/activity قابل ثبت است
```

### 14.4 سناریوی login با password

```text
POST /login/password
  → credential validate
  → risk signals evaluate
  → AuthSession ساخته می‌شود
  → JWT صادر می‌شود
```

### 14.5 Session Management

کاربر می‌تواند sessionهای خودش را ببیند و revoke کند:

```text
GET  /api/v1/auth/sessions/
POST /api/v1/auth/sessions/{session_id}/revoke/
```

ادمین:

```text
GET  /api/v1/auth/admin/users/{user_id}/sessions/
POST /api/v1/auth/admin/users/{user_id}/sessions/revoke-all/
```

### 14.6 Risk Review

```text
GET  /api/v1/auth/admin/risk-signals/
POST /api/v1/auth/admin/risk-signals/{signal_id}/review/
```

### 14.7 API Summary

```text
POST /api/v1/auth/signup/request/
POST /api/v1/auth/signup/verify/
POST /api/v1/auth/register/
POST /api/v1/auth/login/
POST /api/v1/auth/login/password/
POST /api/v1/auth/login/otp/request/
POST /api/v1/auth/login/otp/verify/
POST /api/v1/auth/token/refresh/
POST /api/v1/auth/logout/
GET,PATCH /api/v1/auth/me/
GET,PATCH /api/v1/auth/profile/
POST /api/v1/auth/password/change/
POST /api/v1/auth/password/forgot/request/
POST /api/v1/auth/password/forgot/confirm/
POST /api/v1/auth/identifiers/add/request/
POST /api/v1/auth/identifiers/add/verify/
POST /api/v1/auth/identifiers/make-primary/
GET /api/v1/auth/admin/users/
GET,PATCH,DELETE /api/v1/auth/admin/users/{user_id}/
POST /api/v1/auth/admin/users/{user_id}/role/
```

---

## 15. Public Reports

اپ `public_reports` برای دریافت گزارش‌های عمومی درباره موضوعات تعریف‌شده است.

### 15.1 هدف

یک report ساده نباید فقط یک فرم خام باشد. این app ساختار زیر را فراهم می‌کند:

```text
Subject catalog
Report submission
Attachment support
Admin review
Status transitions
Audit for admin status changes
```

### 15.2 مدل ذهنی

```text
ReportSubject → موضوع قابل انتخاب برای گزارش
PublicReport  → گزارش کاربر/عموم
Attachment    → فایل‌های پشتیبان
Status        → وضعیت بررسی
```

### 15.3 سناریوی کاربر

```text
GET /subjects/
  → کاربر موضوعات فعال را می‌بیند

POST /reports/
  → گزارش ثبت می‌شود
  → attachmentها validate می‌شوند
  → status اولیه در حالت pending قرار می‌گیرد
```

### 15.4 سناریوی ادمین

```text
GET /admin/reports/
  → لیست گزارش‌ها با فیلتر

GET /admin/reports/{id}/
  → جزئیات کامل

PATCH /admin/reports/{id}/status/
  → تغییر وضعیت بررسی
  → audit log ثبت می‌شود
```

### 15.5 APIها

```text
GET  /api/v1/public-reports/subjects/
POST /api/v1/public-reports/reports/
GET  /api/v1/public-reports/admin/reports/
GET  /api/v1/public-reports/admin/reports/{report_id}/
PATCH /api/v1/public-reports/admin/reports/{report_id}/status/
GET,POST /api/v1/public-reports/admin/subjects/
GET,PATCH,DELETE /api/v1/public-reports/admin/subjects/{subject_id}/
```

---

## 16. Tabyin

اپ `tabyin` برای sync و مدیریت محتوای تبیین از source خارجی است.

### 16.1 هدف

به جای ورود دستی محتوا، سیستم می‌تواند از provider خارجی محتوا دریافت کند، normalize کند، hash کند، upsert کند و برای نمایش عمومی آماده کند.

### 16.2 اجزای اصلی

```text
Content مدل محتوای sync شده
UserSubmission محتوای پیشنهادی کاربر
Provider client برای Mohtavanegar
Sync parser
Sync hasher
Sync engine
Celery tasks
Admin sync endpoints
Management command
```

### 16.3 دو حالت sync دستی

از CLI:

```bash
python manage.py sync_tabyin --mode incremental
python manage.py sync_tabyin --mode full
```

PowerShell:

```powershell
python manage.py sync_tabyin --mode incremental
python manage.py sync_tabyin --mode full
```

تفاوت:

```text
incremental → مناسب syncهای دوره‌ای، سریع‌تر، فقط تغییرات جدید/اخیر
full        → مناسب rebuild یا audit کامل source، سنگین‌تر
```

### 16.4 Sync از API ادمین

```text
POST /api/v1/tabyin/admin/sync/
GET  /api/v1/tabyin/admin/sync/status/{task_id}/
```

در حالت async:

```text
API task را dispatch می‌کند
Celery task sync را اجرا می‌کند
status با task_id قابل مشاهده است
```

### 16.5 User submissions

کاربر می‌تواند محتوا پیشنهاد دهد:

```text
GET,POST /api/v1/tabyin/me/submissions/
GET /api/v1/tabyin/me/submissions/{content_id}/
```

ادمین:

```text
GET /api/v1/tabyin/admin/submissions/
POST /api/v1/tabyin/admin/submissions/{content_id}/approve/
POST /api/v1/tabyin/admin/submissions/{content_id}/reject/
```

### 16.6 API Summary

```text
GET /api/v1/tabyin/contents/
GET /api/v1/tabyin/contents/{external_id}/
GET /api/v1/tabyin/admin/contents/
GET /api/v1/tabyin/admin/contents/{external_id}/
PATCH /api/v1/tabyin/admin/contents/{external_id}/toggle/
POST /api/v1/tabyin/admin/sync/
GET /api/v1/tabyin/admin/sync/status/{task_id}/
```

---

## 17. R4J — Reward for Justice

اپ `r4j` یک سیستم Reward for Justice برای نمایش پروفایل مجرمان، دریافت گزارش‌های تکمیلی جامعه، نگه‌داری شواهد و ثبت تعهد جایزه کاربران است.

### 17.1 مفاهیم اصلی

```text
R4JCriminal                  → پروفایل مجرم
R4JCriminalAlias             → نام‌های مستعار
R4JCriminalPhone             → شماره‌ها
R4JCriminalSocial            → شبکه‌های اجتماعی
R4JCriminalPhoto             → تصاویر
R4JCriminalAttachment        → اسناد ادمین
R4JCriminalFieldVisibility   → کنترل visibility فیلدها
R4JReport                    → گزارش کاربر درباره مجرم
R4JReportFieldChange         → پیشنهاد تغییر فیلد
R4JReportAttachment          → ضمیمه گزارش
R4JEvidenceCustodyEvent      → chain-of-custody مدارک
R4JBounty                    → تعهد جایزه کاربر
```

### 17.2 Public Criminal Browse

کاربر عمومی فقط پروفایل‌های `published + active` را می‌بیند. فیلدهای حساس با visibility map کنترل می‌شوند.

```text
GET /api/v1/r4j/criminals/
GET /api/v1/r4j/criminals/{lookup}/
```

`lookup` می‌تواند slug یا id-like باشد.

### 17.3 Admin Criminal Management

ادمین می‌تواند criminal بسازد، ویرایش کند، publish/unpublish کند، و nested resources را مدیریت کند.

```text
GET,POST /api/v1/r4j/admin/criminals/
GET,PATCH,DELETE /api/v1/r4j/admin/criminals/{criminal_id}/
POST /api/v1/r4j/admin/criminals/{criminal_id}/publish/
POST /api/v1/r4j/admin/criminals/{criminal_id}/unpublish/
```

Nested:

```text
aliases
phones
socials
photos
attachments
visibility
```

### 17.4 Report Workflow

کاربر می‌تواند برای یک criminal گزارش تکمیلی بدهد:

```text
POST /api/v1/r4j/criminals/{criminal_id}/reports/
```

گزارش شامل:

```text
notes
field_changes
attachments
```

ادمین می‌تواند report را review کند:

```text
GET  /api/v1/r4j/admin/reports/
GET  /api/v1/r4j/admin/reports/{report_id}/
POST /api/v1/r4j/admin/reports/{report_id}/review/
```

Field-change workflow اجازه می‌دهد بعضی فیلدها approve و بعضی reject شوند؛ یعنی review لزوماً all-or-nothing نیست.

### 17.5 Evidence Chain of Custody

هر attachment مهم `SHA-256` و `file_size` دارد:

```text
R4JCriminalAttachment.file_sha256
R4JCriminalAttachment.file_size
R4JReportAttachment.file_sha256
R4JReportAttachment.file_size
```

برای هر evidence رویداد append-only ساخته می‌شود:

```text
uploaded
hashed
reviewed
transferred
rejected
deleted
```

Admin API:

```text
GET  /api/v1/r4j/admin/evidence-custody/
POST /api/v1/r4j/admin/evidence-custody/{event_id}/review/
```

قواعد:

```text
custody event قابل ویرایش نیست
custody event قابل حذف نیست
هر event دقیقاً به یک evidence target وصل است
review/transfer/reject audit می‌شود
```

### 17.6 Bounty Workflow

کاربر می‌تواند برای criminal جایزه declarative ثبت کند:

```text
POST /api/v1/r4j/criminals/{criminal_id}/bounty/
GET  /api/v1/r4j/me/bounties/
POST /api/v1/r4j/me/bounties/{bounty_id}/cancel/
```

ادمین cancel را approve/reject می‌کند:

```text
GET  /api/v1/r4j/admin/bounties/
GET  /api/v1/r4j/admin/bounties/{bounty_id}/
POST /api/v1/r4j/admin/bounties/{bounty_id}/cancel/approve/
POST /api/v1/r4j/admin/bounties/{bounty_id}/cancel/reject/
```

Denormalized counters روی criminal نگه‌داری می‌شود:

```text
total_bounty_toman
bounties_count
```

### 17.7 محدوده محصول R4J

R4J عمداً سیستم پرونده عملیاتی نیست. محدوده آن به این موارد محدود می‌شود:

```text
- نمایش پروفایل مجرمان منتشرشده
- دریافت گزارش و شواهد تکمیلی از کاربران
- بررسی و اعمال گزارش‌ها توسط ادمین
- نگه‌داری chain-of-custody برای شواهد
- ثبت و مدیریت تعهد جایزه کاربران
```

بنابراین endpointها و مدل‌های مربوط به پرونده عملیاتی از این اپ حذف شده‌اند.

### 17.8 سناریوی end-to-end R4J

```text
1. ادمین criminal draft می‌سازد.
2. عکس، alias، phone، social و attachment اضافه می‌کند.
3. attachment hash و custody event می‌گیرد.
4. ادمین پروفایل را publish می‌کند.
5. کاربر عمومی criminal را می‌بیند.
6. کاربر report با field_changes و attachment ارسال می‌کند.
7. report attachment hash و custody event می‌گیرد.
8. ادمین report را review می‌کند و تغییرات تأییدشده روی پروفایل اعمال می‌شود.
9. کاربر fully-verified برای criminal تعهد جایزه ثبت یا مبلغ آن را به‌روزرسانی می‌کند.
10. در صورت درخواست لغو جایزه یا گزارش، ادمین درخواست را approve/reject می‌کند.
11. همه اقدامات حساس audit و cache invalidation مناسب دارند.
```

---

## 18. Madadkar — Charitable Crowdfunding

اپ `madadkar` مالی‌ترین و حساس‌ترین دامنه پروژه است. طراحی آن فقط campaign/donation ساده نیست؛ شامل reconciliation، refund، adjustment، risk scoring، receipt verification، transparency و financial controls است.

### 18.1 مفاهیم اصلی

```text
Sponsor
Campaign
CampaignImage
Participation
Payment
PaymentRefund
CampaignFinancialAdjustment
MadadkarRiskSignal
DonationReceipt
PaymentReconciliationBatch
PaymentReconciliationItem
CampaignDisbursement
MadadkarFinancialControlSnapshot
```

### 18.2 Campaign Lifecycle

```text
draft → published → completed/closed
```

ادمین:

```text
GET,POST /api/v1/madadkar/admin/campaigns/
GET,PATCH,DELETE /api/v1/madadkar/admin/campaigns/{campaign_id}/
POST /api/v1/madadkar/admin/campaigns/{campaign_id}/publish/
POST /api/v1/madadkar/admin/campaigns/{campaign_id}/close/
```

عمومی:

```text
GET /api/v1/madadkar/campaigns/
GET /api/v1/madadkar/campaigns/{slug}/
```

### 18.3 Participation / Payment

کاربر در campaign مشارکت می‌کند:

```text
POST /api/v1/madadkar/campaigns/{slug}/participate/
```

سپس پرداخت verify می‌شود:

```text
GET,POST /api/v1/madadkar/payment/verify/
```

provider فعلی sandbox/dev-ready است اما workflow برای provider واقعی آماده است.

### 18.4 Refund Workflow

مدل `PaymentRefund` برای refund کنترل‌شده:

```text
requested → approved/rejected → completed
```

API:

```text
GET,POST /api/v1/madadkar/admin/refunds/
POST /api/v1/madadkar/admin/refunds/{refund_id}/{action}/
```

Actionها:

```text
approve
reject
complete
```

قواعد:

```text
refund بدون payment معتبر انجام نمی‌شود
transition نامعتبر رد می‌شود
refund حساس audit می‌شود
```

### 18.5 Financial Adjustments

برای اصلاح مالی campaign بدون دستکاری مستقیم payment ledger:

```text
GET,POST /api/v1/madadkar/admin/adjustments/
POST /api/v1/madadkar/admin/adjustments/{adjustment_id}/{action}/
```

Actionها:

```text
approve
reject
apply
```

### 18.6 Risk Scoring

`MadadkarRiskSignal` برای تشخیص ریسک‌های مالی/رفتاری:

```text
GET  /api/v1/madadkar/admin/risk-signals/
POST /api/v1/madadkar/admin/risk-signals/{signal_id}/review/
```

Signalها برای review انسانی نگه‌داری می‌شوند، نه تصمیم خودکار خطرناک.

### 18.7 Campaign Intelligence

برای insight مدیریتی:

```text
GET /api/v1/madadkar/admin/campaigns/{campaign_id}/intelligence/
GET /api/v1/madadkar/admin/intelligence/overview/
GET /api/v1/madadkar/admin/campaigns/{campaign_id}/analytics/
GET /api/v1/madadkar/admin/campaigns/{campaign_id}/leaderboard/
```

### 18.8 Donation Receipts

هر donation موفق می‌تواند receipt قابل verification داشته باشد:

```text
GET  /api/v1/madadkar/me/receipts/
GET  /api/v1/madadkar/me/receipts/{receipt_id}/
POST /api/v1/madadkar/receipts/verify/
POST /api/v1/madadkar/admin/receipts/{receipt_id}/resend/
```

Verification برای این است که receipt بدون اعتماد blind به UI قابل بررسی باشد.

### 18.9 Reconciliation

برای تطبیق settlement/provider report با ledger داخلی:

```text
POST /api/v1/madadkar/admin/reconciliation/import/
GET  /api/v1/madadkar/admin/reconciliation/batches/
GET  /api/v1/madadkar/admin/reconciliation/batches/{batch_id}/
GET  /api/v1/madadkar/admin/reconciliation/batches/{batch_id}/items/
GET  /api/v1/madadkar/admin/reconciliation/batches/{batch_id}/export/
```

سناریو:

```text
1. فایل reconciliation از provider وارد می‌شود.
2. سیستم ردیف‌ها را با payment داخلی match می‌کند.
3. mismatchها مشخص می‌شوند.
4. batch قابل export و audit است.
```

### 18.10 Disbursement Ledger

برای خروج پول از campaign به beneficiary/هدف:

```text
GET,POST /api/v1/madadkar/admin/disbursements/
GET /api/v1/madadkar/admin/disbursements/{disbursement_id}/
POST /api/v1/madadkar/admin/disbursements/{disbursement_id}/{action}/
GET /api/v1/madadkar/admin/campaigns/{campaign_id}/disbursable/
```

Actionها:

```text
approve
reject
mark-paid
```

### 18.11 Public Transparency

برای اعتماد عمومی:

```text
GET /api/v1/madadkar/campaigns/{slug}/transparency/
```

این endpoint summary مالی public-safe می‌دهد، نه اطلاعات حساس کاربران.

### 18.12 Financial Controls

snapshotهای کنترل مالی:

```text
GET  /api/v1/madadkar/admin/financial-controls/
GET  /api/v1/madadkar/admin/financial-controls/latest/
POST /api/v1/madadkar/admin/financial-controls/generate/
```

Task/command:

```bash
python manage.py generate_madadkar_financial_control
```

Celery task:

```text
apps.madadkar.tasks.generate_financial_control_snapshot_task
```

### 18.13 سناریوی مالی end-to-end

```text
1. ادمین sponsor و campaign می‌سازد.
2. campaign publish می‌شود.
3. کاربر participate می‌کند.
4. payment provider verify انجام می‌دهد.
5. payment موفق ledger را update می‌کند.
6. receipt صادر می‌شود.
7. campaign analytics/intelligence قابل مشاهده است.
8. reconciliation batch وارد می‌شود.
9. mismatchها بررسی می‌شوند.
10. disbursement request ساخته می‌شود.
11. approve/reject/mark-paid audit می‌شود.
12. transparency public-safe نمایش داده می‌شود.
13. financial control snapshot برای نظارت ساخته می‌شود.
```

---

## 19. LMS — Learning Management System

اپ `lms` یک پلتفرم آموزشی کامل است.

### 19.1 مفاهیم اصلی

```text
Category
Course
Lesson
Enrollment
LessonProgress
Question
Answer
DiscussionReport
Quiz
QuizQuestion
QuizOption
QuizAttempt
Certificate
Badge/Skill-oriented data
LessonVideoProcessingJob
LearningActivityStatement
```

### 19.2 Course Lifecycle

ادمین course می‌سازد و publish/archive می‌کند:

```text
GET,POST /api/v1/lms/admin/courses/
GET,PATCH,DELETE /api/v1/lms/admin/courses/{course_id}/
POST /api/v1/lms/admin/courses/{course_id}/publish/
POST /api/v1/lms/admin/courses/{course_id}/archive/
```

کاربر:

```text
GET /api/v1/lms/courses/
GET /api/v1/lms/courses/{slug}/
POST /api/v1/lms/courses/{slug}/enroll/
```

### 19.3 Lessons و Progress

```text
GET /api/v1/lms/courses/{slug}/lessons/
GET /api/v1/lms/courses/{slug}/lessons/{lesson_slug}/
POST /api/v1/lms/lessons/{lesson_id}/progress/
```

Progress service باید enrollment و state را enforce کند.

### 19.4 Signed Media / CDN Readiness

Media access از endpoint کنترل‌شده می‌آید:

```text
GET /api/v1/lms/lessons/{lesson_id}/media/{media_kind}/
```

هدف:

```text
عدم expose مستقیم فایل حساس
قابلیت جایگزینی با signed URL/CDN
audit media access
```

### 19.5 Video Processing Worker

مدل:

```text
LessonVideoProcessingJob
```

Endpoint:

```text
POST /api/v1/lms/admin/lessons/{lesson_id}/video-processing/
GET  /api/v1/lms/admin/lessons/{lesson_id}/video-processing/status/
```

Celery task:

```text
apps.lms.tasks.process_lesson_video_job_task
```

Workflow:

```text
queued → processing → completed/failed/canceled
```

### 19.6 Quiz / Certificate

```text
GET,POST /api/v1/lms/admin/courses/{course_id}/quiz/
POST /api/v1/lms/admin/courses/{course_id}/quiz/publish/
POST /api/v1/lms/courses/{slug}/quiz/start/
GET  /api/v1/lms/quiz/attempts/{attempt_id}/
POST /api/v1/lms/quiz/attempts/{attempt_id}/submit/
GET  /api/v1/lms/certificates/verify/{verification_slug}/
```

### 19.7 Recommendations

```text
GET /api/v1/lms/me/recommendations/
GET /api/v1/lms/admin/recommendations/overview/
```

منطق recommendation می‌تواند بر اساس enrollment، progress، skill gaps و course status خروجی بدهد.

### 19.8 Learning Activity Statements

xAPI-like foundation:

```text
LearningActivityStatement
LearningStatementVerb
```

Endpoint admin:

```text
GET /api/v1/lms/admin/activity-statements/
```

Verbها:

```text
initialized
progressed
completed
passed
failed
certificate_issued
```

### 19.9 Discussion / Q&A

```text
GET,POST /api/v1/lms/lessons/{lesson_id}/questions/
POST /api/v1/lms/questions/{question_id}/answers/
POST /api/v1/lms/questions/{question_id}/answers/{answer_id}/accept/
POST /api/v1/lms/questions/{question_id}/report/
POST /api/v1/lms/answers/{answer_id}/report/
```

ادمین moderation:

```text
PATCH /api/v1/lms/admin/questions/{question_id}/moderate/
PATCH /api/v1/lms/admin/answers/{answer_id}/moderate/
GET   /api/v1/lms/admin/discussion-reports/
PATCH /api/v1/lms/admin/discussion-reports/{report_id}/review/
```

---

## 20. Kindness Wall — Divar-e Mehrabani

اپ `kindness_wall` برای نیاز/کمک، matching، moderation و risk controls است.

### 20.1 مفاهیم اصلی

```text
Category
Listing
Bookmark
Match
ContactReveal
Report
DuplicateReview
Geo/Risk signals
```

### 20.2 Listing Lifecycle

کاربر listing می‌سازد:

```text
GET,POST /api/v1/kindness-wall/me/listings/
GET,PATCH,DELETE /api/v1/kindness-wall/me/listings/{listing_id}/
POST /api/v1/kindness-wall/me/listings/{listing_id}/submit/
POST /api/v1/kindness-wall/me/listings/{listing_id}/close/
POST /api/v1/kindness-wall/me/listings/{listing_id}/renew/
```

ادمین moderate می‌کند:

```text
GET /api/v1/kindness-wall/admin/listings/
GET /api/v1/kindness-wall/admin/listings/{listing_id}/
POST /api/v1/kindness-wall/admin/listings/{listing_id}/approve/
POST /api/v1/kindness-wall/admin/listings/{listing_id}/reject/
POST /api/v1/kindness-wall/admin/listings/{listing_id}/suspend/
POST /api/v1/kindness-wall/admin/listings/{listing_id}/restore/
```

عمومی:

```text
GET /api/v1/kindness-wall/listings/
GET /api/v1/kindness-wall/listings/{slug}/
```

### 20.3 Matching

Matching برای اتصال نیاز و کمک است:

```text
GET /api/v1/kindness-wall/listings/{slug}/matches/
GET /api/v1/kindness-wall/me/matches/
POST /api/v1/kindness-wall/me/matches/{match_id}/contacted/
POST /api/v1/kindness-wall/me/matches/{match_id}/dismiss/
```

منطق matching می‌تواند بر اساس category، location، type، freshness و risk score باشد.

### 20.4 Contact Reveal

برای حفظ privacy، اطلاعات تماس مستقیم از ابتدا public نیست:

```text
POST /api/v1/kindness-wall/listings/{slug}/reveal-contact/
GET  /api/v1/kindness-wall/admin/contact-reveals/
```

### 20.5 Duplicate / Report Review

```text
POST /api/v1/kindness-wall/listings/{slug}/report/
GET  /api/v1/kindness-wall/admin/reports/
POST /api/v1/kindness-wall/admin/reports/{report_id}/review/
GET  /api/v1/kindness-wall/admin/duplicates/
POST /api/v1/kindness-wall/admin/duplicates/{duplicate_id}/review/
```

### 20.6 Export / Analytics

```text
GET /api/v1/kindness-wall/admin/analytics/
GET /api/v1/kindness-wall/admin/listings/export/
GET /api/v1/kindness-wall/admin/reports/export/
```

---

## 21. Support Desk

اپ `support_desk` یک ticketing system کامل با SLA، business calendar، assignment، knowledge base و smart replies است.

### 21.1 مفاهیم اصلی

```text
Department
Category
TicketType
SLAPolicy
BusinessCalendar
Holiday
SupportTicket
SupportMessage
SupportAttachment
Satisfaction
CannedResponse
SupportDuplicateReview
SupportKnowledgeArticle
SupportKnowledgeArticleUse
SmartReply bundle/suggestion
```

### 21.2 Ticket Lifecycle

کاربر draft می‌سازد و submit می‌کند:

```text
GET,POST /api/v1/support/me/tickets/
GET,PATCH /api/v1/support/me/tickets/{ticket_number}/
POST /api/v1/support/me/tickets/{ticket_number}/submit/
POST /api/v1/support/me/tickets/{ticket_number}/reply/
POST /api/v1/support/me/tickets/{ticket_number}/attachments/
POST /api/v1/support/me/tickets/{ticket_number}/reopen/
POST /api/v1/support/me/tickets/{ticket_number}/satisfaction/
GET  /api/v1/support/me/tickets/{ticket_number}/timeline/
```

ادمین:

```text
GET /api/v1/support/admin/tickets/
GET /api/v1/support/admin/tickets/{ticket_number}/
POST /api/v1/support/admin/tickets/{ticket_number}/assign/
POST /api/v1/support/admin/tickets/{ticket_number}/reply/
POST /api/v1/support/admin/tickets/{ticket_number}/internal-note/
POST /api/v1/support/admin/tickets/{ticket_number}/status/
POST /api/v1/support/admin/tickets/{ticket_number}/close/
POST /api/v1/support/admin/tickets/{ticket_number}/escalate/
```

### 21.3 SLA و Business Hours

SLA فقط deadline ساده نیست. Business calendar و holidayها روی محاسبه deadline اثر دارند.

```text
GET,POST /api/v1/support/admin/business-calendars/
PATCH /api/v1/support/admin/business-calendars/{calendar_id}/
GET,POST /api/v1/support/admin/holidays/
PATCH /api/v1/support/admin/holidays/{holiday_id}/
GET,POST /api/v1/support/admin/sla-policies/
PATCH /api/v1/support/admin/sla-policies/{policy_id}/
```

Celery task برای breach:

```text
apps.support_desk.tasks.mark_support_sla_breaches_task
```

### 21.4 Assignment Load Balancing

برای کاهش assignment دستی کورکورانه:

```text
GET  /api/v1/support/admin/tickets/{ticket_number}/assignment-recommendation/
POST /api/v1/support/admin/tickets/{ticket_number}/auto-assign/
```

Recommendation بر اساس workload و context agentها ساخته می‌شود.

### 21.5 Knowledge Base

Public/user-facing:

```text
GET  /api/v1/support/knowledge/articles/
GET  /api/v1/support/knowledge/articles/{slug}/
POST /api/v1/support/knowledge/articles/recommend/
```

Admin:

```text
GET,POST /api/v1/support/admin/knowledge/articles/
GET,PATCH /api/v1/support/admin/knowledge/articles/{article_id}/
POST /api/v1/support/admin/knowledge/articles/{article_id}/publish/
POST /api/v1/support/admin/knowledge/articles/{article_id}/archive/
POST /api/v1/support/admin/knowledge/articles/{article_id}/use/
```

### 21.6 Smart Replies

برای کمک به agent:

```text
GET  /api/v1/support/admin/tickets/{ticket_number}/smart-replies/
POST /api/v1/support/admin/tickets/{ticket_number}/smart-replies/use/
```

Smart replies جایگزین agent نیست؛ پیشنهاد operational است و use آن audit/activity می‌شود.

### 21.7 Export و Analytics

```text
GET /api/v1/support/admin/analytics/
GET /api/v1/support/admin/export/tickets/
GET /api/v1/support/admin/export/messages/
GET /api/v1/support/admin/export/sla/
GET /api/v1/support/admin/export/csat/
```

---

## 22. Celery، Redis، Cache و Job Scheduling

### 22.1 Queueها

```text
default      → tasks عمومی، notifications، support maintenance، LMS processing
tabyin_sync  → sync محتوای تبیین
madadkar     → عملیات scheduled مالی/کمپین
```

`docker-compose.yml` worker را با queueهای زیر اجرا می‌کند:

```text
default,tabyin_sync,madadkar
```

### 22.2 Task routing

در `config/settings/base.py`:

```text
apps.tabyin.tasks.sync_tabyin_incremental_task       → tabyin_sync
apps.tabyin.tasks.sync_tabyin_full_task              → tabyin_sync
apps.madadkar.tasks.expire_stale_participations_task → madadkar
apps.madadkar.tasks.close_expired_campaigns_task     → madadkar
apps.madadkar.tasks.generate_financial_control_snapshot_task → madadkar
apps.lms.tasks.process_lesson_video_job_task         → default
apps.support_desk.tasks.*                            → default
apps.notifications.tasks.dispatch_notification_event_task → default
```

### 22.3 Beat schedule

Celery Beat برای jobهای دوره‌ای مثل:

```text
Tabyin incremental sync
Madadkar stale participation expiry
Madadkar expired campaign close
Madadkar financial control snapshot
Support SLA breach marking
Support draft cleanup/digest
```

---

## 23. Media، Object Storage و CDN Readiness

### 23.1 Local media

در development/local:

```text
MEDIA_ROOT=/app/media یا media/
MEDIA_URL=/media/
```

### 23.2 S3/MinIO compatible

برای production:

```env
MEDIA_STORAGE_BACKEND=s3
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_STORAGE_BUCKET_NAME=...
AWS_S3_ENDPOINT_URL=...
AWS_S3_REGION_NAME=...
MEDIA_CDN_DOMAIN=cdn.example.com
```

### 23.3 امنیت فایل

فایل‌ها در دامنه‌های مختلف validate می‌شوند:

```text
R4J evidence attachments
Support attachments
Public report attachments
Madadkar campaign images
LMS media
Kindness Wall images
```

برای evidenceهای R4J، hash و custody event نیز ثبت می‌شود.

---

## 24. Observability، Health و Metrics

### 24.1 Logging

```env
LOG_FORMAT=text
# یا production:
LOG_FORMAT=json
```

### 24.2 Sentry

```env
SENTRY_DSN=...
SENTRY_ENVIRONMENT=production
```

اگر DSN خالی باشد initialize نمی‌شود.

### 24.3 OpenTelemetry

پروژه env-driven readiness دارد. اگر exporter/provider تنظیم شود، tracing قابل فعال‌سازی است.

### 24.4 Prometheus

```text
GET /api/v1/metrics/
```

### 24.5 Health Strategy

```text
/health/        → health پایه
/health/ready/  → readiness برای container/orchestrator
/health/detailed/ → diagnostic کامل برای admin/ops
```

---

## 25. سناریوهای عملیاتی انتها به انتها

### 25.1 سناریوی Auth تا Activity

```text
1. کاربر signup/request می‌زند.
2. OTPChallenge ساخته و ارسال می‌شود.
3. signup/verify کاربر را فعال می‌کند.
4. JWT صادر می‌شود.
5. AuthSession ساخته می‌شود.
6. activity timeline قابل نمایش است.
7. اگر risk anomaly باشد AuthRiskSignal ساخته می‌شود.
8. ادمین risk signal را review می‌کند.
```

### 25.2 سناریوی Madadkar مالی

```text
1. campaign ساخته و publish می‌شود.
2. کاربر participate می‌کند.
3. payment verify می‌شود.
4. receipt صادر می‌شود.
5. reconciliation batch وارد می‌شود.
6. risk signal یا mismatch review می‌شود.
7. disbursement approve و paid می‌شود.
8. transparency endpoint public-safe خروجی می‌دهد.
9. financial control snapshot ساخته می‌شود.
```

### 25.3 سناریوی R4J گزارش و جایزه

```text
1. criminal ساخته و publish می‌شود.
2. کاربر report و evidence ارسال می‌کند.
3. evidence hash و custody chain می‌گیرد.
4. ادمین report را review می‌کند و تغییرات معتبر را اعمال می‌کند.
5. کاربر fully-verified bounty declarative ثبت یا ویرایش می‌کند.
6. درخواست‌های لغو report/bounty توسط ادمین approve یا reject می‌شوند.
```

### 25.4 سناریوی Support Desk

```text
1. کاربر ticket draft می‌سازد.
2. ticket submit می‌شود و SLA due محاسبه می‌شود.
3. assignment recommendation ساخته می‌شود.
4. agent auto-assign می‌کند.
5. smart replies پیشنهاد می‌شوند.
6. agent reply/internal note/status change انجام می‌دهد.
7. user satisfaction ثبت می‌کند.
8. SLA/CSAT export برای مدیر قابل دریافت است.
```

### 25.5 سناریوی LMS

```text
1. ادمین course/lesson/quiz می‌سازد.
2. course publish می‌شود.
3. کاربر enroll می‌کند.
4. lesson media از endpoint کنترل‌شده access می‌شود.
5. progress ثبت می‌شود.
6. learning activity statement ساخته می‌شود.
7. quiz attempt submit می‌شود.
8. certificate صادر و verify می‌شود.
9. recommendation endpoint مسیر بعدی را پیشنهاد می‌دهد.
```

---

## 26. Production Runbooks

مستندات عملیاتی production در مسیر `docs/production/` نگه‌داری می‌شوند و README فقط خلاصه اجرایی آن‌هاست. فایل‌های کلیدی:

```text
docs/production/ENVIRONMENT_MATRIX.md
docs/production/DEPLOYMENT_RUNBOOK.md
docs/production/BACKUP_RESTORE_RUNBOOK.md
docs/production/INCIDENT_RESPONSE_RUNBOOK.md
docs/production/SECRET_ROTATION_RUNBOOK.md
docs/production/RELEASE_CHECKLIST.md
docs/production/PRODUCTION_10_10_STATUS.md
```

برای release واقعی، مخصوصاً این سه فایل باید قبل از deploy خوانده شوند:

```text
docs/production/DEPLOYMENT_RUNBOOK.md
docs/production/BACKUP_RESTORE_RUNBOOK.md
docs/production/PRODUCTION_10_10_STATUS.md
```

### 26.1 اولین deploy

```bash
cp .env.example .env
# envها را تنظیم کن
make verify
docker-compose up --build -d
docker-compose logs -f web
```

### 26.2 migration در container

در compose فعلی web با `RUN_MIGRATIONS=1` migration را هنگام start اجرا می‌کند. برای کنترل دستی:

```bash
docker-compose exec web python manage.py migrate
```

### 26.3 collectstatic

```bash
docker-compose exec web python manage.py collectstatic --noinput
```

### 26.4 ساخت superuser در Docker

```bash
docker-compose exec web python manage.py createsuperuser
```

### 26.5 بررسی health

```bash
curl http://127.0.0.1:8000/api/v1/health/
curl http://127.0.0.1:8000/api/v1/health/ready/
curl http://127.0.0.1:8000/api/v1/health/detailed/
```

### 26.6 بررسی Celery

```bash
docker-compose logs -f worker
docker-compose exec worker celery -A config inspect ping
```

Flower:

```text
http://127.0.0.1:5555/
```

### 26.7 Audit chain verification

```bash
python manage.py verify_audit_chain
```

### 26.8 Audit package export

```bash
python manage.py export_audit_package --output ./audit_exports
```

### 26.9 Tabyin sync دستی

```bash
python manage.py sync_tabyin --mode incremental
python manage.py sync_tabyin --mode full
```

### 26.10 Madadkar financial control

```bash
python manage.py generate_madadkar_financial_control
```

---

## 27. چک‌لیست Production

قبل از production واقعی:

```text
SECRET_KEY قوی و محرمانه تنظیم شده باشد
DEBUG=False باشد
ALLOWED_HOSTS واقعی باشد
CSRF_TRUSTED_ORIGINS واقعی باشد
CORS_ALLOWED_ORIGINS محدود باشد
PostgreSQL production آماده باشد
Redis production آماده باشد
Email SMTP واقعی تنظیم شده باشد
SMS provider بعد از مجوز فعال شود
Payment provider بعد از مجوز فعال شود
S3/MinIO/CDN برای media تصمیم‌گیری شود
Sentry/Logging/Monitoring تنظیم شود
Backup strategy برای DB و media مشخص باشد
Audit export و retention policy مشخص باشد
TLS/Reverse proxy تنظیم شود
make verify قبل از release پاس شود
schema.yaml با API واقعی sync باشد
```

---

## 28. نقشه فایل‌ها و مسئولیت هر بخش

```text
README.md                         → مستند اصلی پروژه
STRUCTURE.md                      → ساختار پروژه
Makefile                          → quality/operation commands
Dockerfile                        → production runtime image
docker-compose.yml                → local production-like orchestration
entrypoint.sh                     → container bootstrapping
.env.example                      → reference env config
schema.yaml                       → committed OpenAPI schema
pyproject.toml                    → pytest/ruff/coverage config
requirements.txt                  → production dependencies
requirements-dev.txt              → dev/security/test dependencies
.github/workflows/ci.yml          → GitHub Actions quality gate
config/settings/base.py           → shared settings
config/settings/development.py    → dev settings
config/settings/production.py     → production settings
config/urls.py                    → root routing
apps/core                         → shared infra
apps/authentication               → identity/auth/session/risk
apps/public_reports               → public reports
apps/tabyin                       → content sync/submissions
apps/audit_logs                   → audit/forensics
apps/r4j                          → reward for justice criminal profiles/reports/bounties/evidence
apps/madadkar                     → charitable finance platform
apps/lms                          → learning platform
apps/kindness_wall                → kindness listings/matching
apps/support_desk                 → ticketing/SLA/KB/smart replies
apps/notifications                → notification engine
apps/activity                     → user/admin activity timeline
apps/command_center               → unified admin overview
frontend                          → Next.js/UI layer
```

---

## 29. اصل نهایی مهندسی پروژه

این پروژه با این فرض نوشته شده است:

```text
اگر چیزی حساس است، audit شود.
اگر چیزی state را تغییر می‌دهد، service شود.
اگر چیزی read پیچیده است، selector شود.
اگر چیزی public API است، OpenAPI آن تمیز باشد.
اگر چیزی production است، verify باید آن را ثابت کند.
```

این README باید همراه با رشد پروژه زنده بماند؛ هر feature بزرگ جدید باید همراه با توضیح معماری، سناریو، endpoint و runbook لازم در همین سند یا docs اختصاصی ثبت شود.
