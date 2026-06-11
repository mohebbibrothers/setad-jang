# ستاد جنگ — Setad Jang Enterprise Backend

<p align="center">
  <strong>Enterprise-grade, production-minded Django REST Framework backend</strong><br />
  Django 6 · DRF · PostgreSQL · Redis · Celery · OpenAPI · JWT · Audit Trail · Payment Ledger · LMS
</p>

<p align="center">
  <img alt="Django" src="https://img.shields.io/badge/Django-6.x-0C4B33?style=for-the-badge&logo=django&logoColor=white" />
  <img alt="DRF" src="https://img.shields.io/badge/DRF-3.x-A30000?style=for-the-badge" />
  <img alt="Celery" src="https://img.shields.io/badge/Celery-5.x-37814A?style=for-the-badge&logo=celery&logoColor=white" />
  <img alt="PostgreSQL" src="https://img.shields.io/badge/PostgreSQL-production-4169E1?style=for-the-badge&logo=postgresql&logoColor=white" />
  <img alt="Tests" src="https://img.shields.io/badge/tests-928%2B%20passed-brightgreen?style=for-the-badge" />
  <img alt="OpenAPI" src="https://img.shields.io/badge/OpenAPI-clean-blue?style=for-the-badge" />
</p>

---

## فهرست

- [1. پروژه چیست؟](#1-پروژه-چیست)
- [2. وضعیت فعلی کیفیت](#2-وضعیت-فعلی-کیفیت)
- [3. معماری کلان](#3-معماری-کلان)
- [4. اپ‌ها و قابلیت‌ها](#4-اپها-و-قابلیتها)
- [5. LMS — سامانه آموزش بعثت مردم](#5-lms--سامانه-آموزش-بعثت-مردم)
- [6. Observability و Health](#6-observability-و-health)
- [7. Logging و Auditability](#7-logging-و-auditability)
- [8. Celery و Background Jobs](#8-celery-و-background-jobs)
- [9. Docker و Production Runtime](#9-docker-و-production-runtime)
- [10. نصب و اجرای Local](#10-نصب-و-اجرای-local)
- [11. Quality Gate و CI/CD](#11-quality-gate-و-cicd)
- [12. OpenAPI Documentation](#12-openapi-documentation)
- [13. Production Checklist](#13-production-checklist)
- [14. فلسفه مهندسی پروژه](#14-فلسفه-مهندسی-پروژه)

---

## 1. پروژه چیست؟

**Setad Jang** یک backend چنددامنه‌ای، بزرگ، modular و production-minded است که برای نمایش توانمندی سطح senior در طراحی و پیاده‌سازی backend ساخته شده است.

هدف پروژه فقط پیاده‌سازی endpoint نیست؛ هدف این است که هر بخش از سیستم از نظرهای زیر قابل دفاع باشد:

```text
Architecture
Security
Correctness
Testing
Observability
Auditability
Performance
Operational readiness
Developer experience
```

این پروژه چندین دامنه مستقل اما هماهنگ را پوشش می‌دهد:

| App | هدف |
|---|---|
| `core` | زیرساخت مشترک، response envelope، pagination، health، cache، exception handling |
| `authentication` | احراز هویت چندشناسه‌ای email/phone، OTP امن، JWT، profile |
| `public_reports` | گزارشات مردمی، subjectها، attachmentها، workflow بررسی |
| `tabyin` | بانک محتوای تبیین، sync از Armansky، ارسال محتوا توسط کاربر و review ادمین |
| `audit_logs` | audit trail append-only و forensic-grade |
| `r4j` | Reward for Justice، پروفایل مجرم، گزارش community، bounty |
| `madadkar` | crowdfunding خیریه سهم‌محور، payment gateway، Zarinpal، ledger مالی |
| `lms` | سامانه آموزش بعثت مردم، دوره، جلسه، آزمون، مدرک، مهارت، گزارش مدیریتی |

---

## 2. وضعیت فعلی کیفیت

آخرین quality gate موفق پروژه:

```bash
make verify
```

خروجی آخرین verification:

```text
python -m pip check                              ✅ No broken requirements
python -m ruff check .                           ✅ All checks passed
python manage.py check                           ✅ No issues
python manage.py check --deploy                  ✅ No issues
python manage.py makemigrations --check --dry-run ✅ No changes detected
python manage.py spectacular --validate          ✅ Clean OpenAPI schema
pytest -q                                        ✅ 928+ passed
```

پروژه با policyهای سخت‌گیرانه نگهداری می‌شود:

```text
Zero-warning policy
No placeholder / TODO / pass in production code
No direct DB mutation in views
Service layer owns mutations
Selector layer owns read queries
Audit log for sensitive operations
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
      ├── Views              → HTTP orchestration only
      ├── Serializers        → input/output contracts + validation
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

اصل محوری:

> View فقط مرز HTTP است. منطق واقعی در service/selector layer قرار دارد.

---

## 4. اپ‌ها و قابلیت‌ها

### 4.1 Core

زیرساخت مشترک پروژه:

- `BaseModel` با `created_at`, `updated_at`, `is_active`
- soft delete managers
- unified response envelope
- custom pagination
- custom exception handler
- request ID middleware
- health/liveness/readiness/detailed endpoints
- cache helpers با namespace versioning
- OpenAPI schema helpers

Response envelope:

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

قابلیت‌ها:

- Custom User model
- ثبت‌نام با email یا phone
- password login و OTP login
- JWT access/refresh با rotation و blacklist
- profile تکمیلی
- primary identifier switching
- اتصال identifier دوم
- legacy endpoint deprecation

امنیت OTP:

- OTP plain در DB ذخیره نمی‌شود
- HMAC/SHA-256 hashing
- replay protection
- race-safe conditional update
- attempt limit با DB-side `F()` expression
- cooldown per identifier/purpose
- provider pattern برای email/SMS
- honeypot ضد bot
- global OTP anomaly guard
- identifier masking در logs

---

### 4.3 Public Reports

- subjectهای قابل مدیریت توسط ادمین
- ثبت گزارش عمومی با attachment
- privacy-safe public response
- state machine وضعیت گزارش
- audit برای create/update/delete/status change
- upload validation
- admin filters و pagination
- operational indexes

State machine:

```text
PENDING   → REVIEWING / APPROVED / REJECTED
REVIEWING → PENDING / APPROVED / REJECTED
APPROVED  → terminal
REJECTED  → terminal
```

---

### 4.4 Tabyin

دو منبع محتوا دارد:

```text
External crawled content → auto-approved
User-submitted content   → pending review → admin approve/reject
```

قابلیت‌ها:

- sync کامل و افزایشی از Armansky/Mohtavanegar
- provider pattern
- HTTP retry/backoff
- content hashing برای change detection
- bulk DB operations
- soft delete برای محتوای حذف‌شده در منبع
- Celery scheduled sync
- cache-aware public selectors
- admin toggle
- async sync dispatch + task status endpoint
- user submission workflow
- admin review workflow
- audit actions برای submit/approve/reject

---

### 4.5 Audit Logs

Audit trail پروژه forensic-grade است:

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

دامنه R4J:

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

سیستم crowdfunding خیریه سهم‌محور:

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

- SandboxProvider برای تست/dev
- ZarinpalProvider واقعی با HTTP integration
- idempotent verify
- amount tampering detection
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

---

## 5. LMS — سامانه آموزش بعثت مردم

LMS جدیدترین و کامل‌ترین اپ پروژه است؛ یک سامانه آموزش رایگان برای «بعثت مردم» که شامل دسته‌بندی، کلاس، جلسه، ثبت‌نام، پیشرفت، پرسش‌وپاسخ، آزمون حرفه‌ای، مدرک قابل اعتبارسنجی و مهارت/مدال پروفایل است.

### 5.1 هدف LMS

کاربر بتواند:

- کلاس‌های منتشرشده را ببیند
- در کلاس رایگان ثبت‌نام کند
- جلسات را دنبال کند
- progress خود را ببیند
- سؤال بپرسد و پاسخ بگیرد
- آزمون بدهد
- در صورت قبولی مدرک بگیرد
- مهارت/مدال را در پروفایل داشته باشد

ادمین بتواند:

- دسته‌بندی بسازد
- کلاس بسازد
- جلسه بسازد
- آزمون بسازد
- سؤال و گزینه صحیح را تعریف کند
- گزارش کامل کلاس را ببیند
- Excel export بگیرد
- مدرک را revoke کند
- کاربر قفل‌شده در آزمون را unlock کند

---

### 5.2 دسته‌بندی‌های پویا

دسته‌بندی‌ها hard-code نیستند. ادمین می‌تواند هر دسته‌ای بسازد:

```text
برنامه‌نویسی
ادیت عکس
ادیت فیلم
زبان
هوش مصنوعی
سایر
...
```

مدل:

```text
LMSCategory
```

فیلدها:

```text
title
slug
description
icon
cover_image
order
is_active
```

---

### 5.3 کلاس‌ها / Courses

مدل:

```text
Course
```

فیلدهای مهم:

```text
category
title
slug
subtitle
short_description
description
cover_image
instructor_name
instructor_bio
instructor_avatar
level
status
language
is_featured
intro_video_url
estimated_duration_seconds
lessons_count
enrollments_count
graduates_count
average_rating
published_at
archived_at
```

State machine:

```text
DRAFT → PUBLISHED → ARCHIVED
```

فقط courseهای `PUBLISHED` در public API نمایش داده می‌شوند.

---

### 5.4 جلسات / Lessons

مدل:

```text
Lesson
```

هر جلسه از hybrid media پشتیبانی می‌کند:

```text
video_provider
video_url
embed_url
video_file
duration_seconds
transcript
summary
homework
attachment_file
attachment_title
is_preview
```

یعنی جلسه می‌تواند با:

- لینک مستقیم
- embed URL
- فایل ویدئو
- جزوه/attachment

مدیریت شود.

---

### 5.5 ثبت‌نام رایگان

ثبت‌نام پولی نیست؛ فقط برای tracking است.

مدل:

```text
Enrollment
```

کاربر برای ثبت‌نام باید:

```text
authenticated باشد
first_name داشته باشد
last_name داشته باشد
profile.national_code داشته باشد
```

ثبت‌نام idempotent است:

```text
بار اول  → 201 Created
بار دوم → 200 OK و همان enrollment قبلی
```

---

### 5.6 Progress Tracking

مدل:

```text
LessonProgress
```

رفتار حرفه‌ای:

```text
watched_seconds فقط افزایش پیدا می‌کند
last_position_seconds می‌تواند عقب/جلو برود
```

مثلاً اگر کاربر ۸۰ ثانیه دیده باشد و بعد rewind کند:

```text
watched_seconds = 80
last_position_seconds = 10
```

Progress کل کلاس از کل duration جلسات محاسبه می‌شود، نه فقط جلسات شروع‌شده.

آستانه تکمیل جلسه:

```text
90%
```

---

### 5.7 پرسش‌وپاسخ جلسات

مدل‌ها:

```text
LessonQuestion
LessonAnswer
LessonDiscussionReport
```

قواعد:

- فقط ثبت‌نام‌شده‌ها می‌توانند سؤال/پاسخ ثبت کنند.
- سؤال بلافاصله visible است.
- پاسخ‌ها threaded هستند.
- صاحب سؤال یا ادمین می‌تواند پاسخ را accepted کند.
- کاربر می‌تواند سؤال/پاسخ را report کند.
- ادمین می‌تواند hide/delete/flag/pin/review کند.

وضعیت‌ها:

```text
VISIBLE
HIDDEN
DELETED
FLAGGED
```

---

### 5.8 آزمون حرفه‌ای و زمان‌دار

آزمون فقط توسط ادمین ساخته می‌شود.

کاربر هیچ دسترسی‌ای برای ساخت quiz/question/option ندارد.

مدل‌ها:

```text
Quiz
QuizQuestion
QuizOption
QuizAttempt
QuizAnswer
QuizUnlock
```

ویژگی‌ها:

- آزمون برای هر course
- سؤال‌ها وزن‌دار
- گزینه‌ها single-choice
- هر سؤال دقیقاً یک گزینه صحیح
- ادمین `time_limit_minutes` را تعیین می‌کند
- ادمین `passing_score` را تعیین می‌کند
- default قبولی: `12/20`
- default تلاش‌ها: `2`
- default retake delay: `14 days`

هنگام start آزمون:

```text
expires_at = now + time_limit_minutes
question_snapshot ساخته می‌شود
option_order_snapshot ساخته می‌شود
```

هنگام submit:

- اگر زمان تمام شده باشد، attempt منقضی می‌شود.
- پاسخ‌ها با snapshot validate می‌شوند.
- نمره weighted از ۲۰ محاسبه می‌شود.

قانون مهم:

```text
پاسخ صحیح و explanation قبل از قبولی نمایش داده نمی‌شود.
```

اگر کاربر fail کند، جواب درست را نمی‌بیند و نمی‌تواند برای تلاش دوم حفظ کند.

---

### 5.9 Certificate و PDF رسمی

بعد از قبولی آزمون:

- certificate صادر می‌شود
- PDF رسمی ساخته می‌شود
- certificate verification code ساخته می‌شود
- public verification endpoint فعال است
- skill/badge ساخته می‌شود

مدل:

```text
Certificate
```

Snapshotها:

```text
full_name_snapshot
gender_snapshot
national_code_snapshot
course_title_snapshot
instructor_name_snapshot
score_out_of_20
```

برای آقا/خانم از `Profile.gender` استفاده می‌شود.

نمونه PDF مدرک:

```text
docs/assets/lms/basat_mardom_certificate_sample.pdf
```

لوگوی استفاده‌شده:

```text
static/lms/certificates/basat_mardom_logo.jpg
```

---

### 5.10 Public Certificate Verification

Endpoint عمومی:

```text
GET /api/v1/lms/certificates/verify/{verification_slug}/
```

اگر مدرک معتبر باشد:

- certificate code
- نام کاربر snapshot
- کد ملی snapshot
- عنوان کلاس snapshot
- نام استاد snapshot
- نمره
- متن رسمی مدرک

نمایش داده می‌شود.

اگر revoke شده باشد:

```text
404
```

---

### 5.11 مهارت‌ها و مدال‌ها

بعد از صدور certificate، مهارت کاربر ساخته می‌شود:

```text
LMSUserSkill
```

مدال‌ها بر اساس نمره:

```text
12 تا 15.99   BRONZE
16 تا 17.99   SILVER
18 تا 19.49   GOLD
19.5 تا 20    DISTINCTION
```

این مهارت‌ها در پروفایل کاربر قابل نمایش‌اند.

Endpoint:

```text
GET /api/v1/lms/me/skills/
```

---

### 5.12 گزارش ادمین، Leaderboard و Export

ادمین برای هر کلاس گزارش دارد:

```text
GET /api/v1/lms/admin/courses/{id}/report/
GET /api/v1/lms/admin/courses/{id}/analytics/
GET /api/v1/lms/admin/courses/{id}/leaderboard/
GET /api/v1/lms/admin/courses/{id}/export/
```

Analytics:

```text
participants_count
active_count
completed_count
graduates_count
average_progress_percent
quiz_attempts_count
quiz_passed_count
quiz_failed_count
average_score_out_of_20
```

Leaderboard:

```text
user_id
full_name
email
progress_percent
best_score_out_of_20
badge_level
certificate_code
```

Export:

- Excel `.xlsx`
- RTL sheet
- styled headers
- participant rows
- certificate code
- audit action:

```text
LMS_COURSE_REPORT_EXPORTED
```

---

### 5.13 LMS Endpoint Summary

Public:

```text
GET /api/v1/lms/categories/
GET /api/v1/lms/categories/{slug}/
GET /api/v1/lms/courses/
GET /api/v1/lms/courses/{slug}/
GET /api/v1/lms/courses/{slug}/lessons/
GET /api/v1/lms/courses/{slug}/lessons/{lesson_slug}/
GET /api/v1/lms/certificates/verify/{verification_slug}/
```

User:

```text
POST /api/v1/lms/courses/{slug}/enroll/
GET  /api/v1/lms/me/enrollments/
GET  /api/v1/lms/me/enrollments/{id}/
POST /api/v1/lms/lessons/{id}/progress/
GET  /api/v1/lms/me/skills/
GET  /api/v1/lms/me/certificates/
GET  /api/v1/lms/me/certificates/{id}/
```

Q&A:

```text
GET  /api/v1/lms/lessons/{id}/questions/
POST /api/v1/lms/lessons/{id}/questions/
POST /api/v1/lms/questions/{id}/answers/
POST /api/v1/lms/questions/{id}/answers/{answer_id}/accept/
POST /api/v1/lms/questions/{id}/report/
POST /api/v1/lms/answers/{id}/report/
```

Quiz:

```text
GET  /api/v1/lms/courses/{slug}/quiz/
POST /api/v1/lms/courses/{slug}/quiz/start/
GET  /api/v1/lms/quiz/attempts/{id}/
POST /api/v1/lms/quiz/attempts/{id}/submit/
```

Admin:

```text
CRUD categories
CRUD courses
publish/archive courses
CRUD lessons
quiz builder
question/options builder
quiz publish
quiz unlock
certificate revoke
course report
course analytics
course leaderboard
Excel export
Q&A moderation
```

---

## 6. Observability و Health

سه سطح health داریم:

```text
GET /api/v1/health/           → liveness
GET /api/v1/health/ready/     → readiness
GET /api/v1/health/detailed/  → detailed diagnostics
```

Readiness dependencyهای critical را چک می‌کند:

- database
- cache
- Celery broker

Health responseها secret-safe هستند و credential/traceback خام leak نمی‌کنند.

---

## 7. Logging و Auditability

فرمت logging:

```text
{asctime} [{levelname}] [{request_id}] {name}: {message}
```

قواعد مهم:

- هر request یک request_id دارد.
- PII و identifierها در لاگ mask می‌شوند.
- OTP/token/password وارد audit/log نمی‌شود.
- health degraded/error component-level logging دارد.
- payment mismatch با error-level ثبت می‌شود.
- audit metadata برای incident review ذخیره می‌شود.

---

## 8. Celery و Background Jobs

Celery برای taskهای async و scheduled استفاده می‌شود:

```text
tabyin sync incremental
tabyin sync full
audit log async write
madadkar stale participation expiration
madadkar expired campaign close
LMS certificate PDF task extension point
```

Queueها:

```text
default
tabyin_sync
madadkar
```

---

## 9. Docker و Production Runtime

سرویس‌ها:

```text
web       → Django/Gunicorn
postgres  → PostgreSQL
redis     → cache + broker
worker    → Celery worker
beat      → Celery beat
flower    → Celery monitoring
```

Healthcheck کانتینر web روی readiness است:

```text
/api/v1/health/ready/
```

---

## 10. نصب و اجرای Local

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
make install
python manage.py migrate
python manage.py runserver
```

یا مستقیم:

```bash
pip install -r requirements.txt -r requirements-dev.txt
python manage.py migrate
python manage.py runserver
```

---

## 11. Quality Gate و CI/CD

دستور اصلی:

```bash
make verify
```

اجرا می‌کند:

```text
pip check
ruff check .
python manage.py check
python manage.py check --deploy
python manage.py makemigrations --check --dry-run
python manage.py spectacular --validate
pytest -q
```

GitHub Actions:

```text
.github/workflows/ci.yml
```

شامل:

- PostgreSQL service container
- Redis service container
- Python 3.14
- pip cache
- dependency install
- pip check
- Ruff
- Django check
- deploy check
- migration drift check
- OpenAPI schema validation
- full pytest
- schema artifact upload

---

## 12. OpenAPI Documentation

بعد از اجرای سرور:

```text
Swagger UI : /api/docs/
ReDoc      : /api/redoc/
Schema     : /api/schema/
```

برای regenerate:

```bash
make schema-update
```

---

## 13. Production Checklist

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
SMS provider واقعی
Object storage برای media در مقیاس production
```

---

## 14. فلسفه مهندسی پروژه

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
