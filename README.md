# ستاد جنگ — Setad Jang Enterprise Backend

<p align="center">
  <strong>Enterprise-grade, production-minded Django REST Framework backend</strong><br />
  Django 6 · DRF · PostgreSQL · Redis · Celery · OpenAPI · JWT · Audit Trail · Payment Ledger · LMS · Kindness Wall · Support Desk
</p>

<p align="center">
  <img alt="Django" src="https://img.shields.io/badge/Django-6.x-0C4B33?style=for-the-badge&logo=django&logoColor=white" />
  <img alt="DRF" src="https://img.shields.io/badge/DRF-3.x-A30000?style=for-the-badge" />
  <img alt="Celery" src="https://img.shields.io/badge/Celery-5.x-37814A?style=for-the-badge&logo=celery&logoColor=white" />
  <img alt="PostgreSQL" src="https://img.shields.io/badge/PostgreSQL-production-4169E1?style=for-the-badge&logo=postgresql&logoColor=white" />
  <img alt="Tests" src="https://img.shields.io/badge/tests-1032%2B%20passed-brightgreen?style=for-the-badge" />
  <img alt="OpenAPI" src="https://img.shields.io/badge/OpenAPI-clean-blue?style=for-the-badge" />
</p>

---

## فهرست

- [1. پروژه چیست؟](#1-پروژه-چیست)
- [2. وضعیت فعلی کیفیت](#2-وضعیت-فعلی-کیفیت)
- [3. معماری کلان](#3-معماری-کلان)
- [4. اپ‌ها و قابلیت‌ها](#4-اپها-و-قابلیتها)
- [5. LMS — سامانه آموزش بعثت مردم](#5-lms--سامانه-آموزش-بعثت-مردم)
- [6. Kindness Wall — دیوار مهربانی](#6-kindness-wall--دیوار-مهربانی)
- [7. Support Desk — میز پشتیبانی](#7-support-desk--میز-پشتیبانی)
- [8. Observability و Health](#8-observability-و-health)
- [9. Logging و Auditability](#9-logging-و-auditability)
- [10. Celery و Background Jobs](#10-celery-و-background-jobs)
- [11. Docker و Production Runtime](#11-docker-و-production-runtime)
- [12. نصب و اجرای Local](#12-نصب-و-اجرای-local)
- [13. Quality Gate و CI/CD](#13-quality-gate-و-cicd)
- [14. OpenAPI Documentation](#14-openapi-documentation)
- [15. Production Checklist](#15-production-checklist)
- [16. فلسفه مهندسی پروژه](#16-فلسفه-مهندسی-پروژه)

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
| `kindness_wall` | دیوار مهربانی، آگهی کمک/نیاز، دسته‌بندی درختی، matching، contact reveal امن، گزارش و analytics |
| `support_desk` | میز پشتیبانی enterprise، تیکت، SLA، دسته‌بندی درختی، مکالمه، internal note، export و analytics |

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
pytest -q                                        ✅ 1032+ passed
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

## 6. Kindness Wall — دیوار مهربانی

دیوار مهربانی یک اپ آگهی‌محور شبیه Divar است، اما بدون خریدوفروش و بدون تراکنش مالی. هدف آن اتصال انسانی بین دو نوع ثابت آگهی است:

```text
نیاز به کمک دارم     → need_help
می‌خواهم کمک کنم    → offer_help
```

### 6.1 اصول طراحی

- دسته‌بندی‌ها dynamic و tree-based هستند و توسط ادمین مدیریت می‌شوند.
- کاربر فقط در صورت login، شماره موبایل تأییدشده و پروفایل هویتی کامل می‌تواند آگهی ثبت کند.
- آگهی ابتدا draft است، سپس برای review ارسال می‌شود و فقط بعد از approval منتشر می‌شود.
- public list/detail هیچ‌وقت شماره تماس خام را expose نمی‌کند.
- مشاهده شماره تماس فقط از endpoint اختصاصی، فقط برای authenticated user، همراه با audit row انجام می‌شود.
- owner نمی‌تواند با reveal-contact آگهی خودش metrics را inflate کند؛ شماره خودش را از dashboard مالک می‌بیند.
- mutationها در service layer هستند؛ views فقط orchestration HTTP انجام می‌دهند.
- selectors مسئول queryهای optimized با `select_related` و `prefetch_related` هستند.

### 6.2 مدل‌های اصلی

```text
KindnessCategory            → دسته‌بندی درختی ادمین‌محور
KindnessListing             → آگهی اصلی کمک/نیاز
KindnessListingImage        → تصویر کاور/گالری
KindnessTag                 → فرهنگ تگ نرمال‌شده
KindnessKeywordAlias        → synonym/alias برای matching فارسی
KindnessMatch               → match materialized بین آگهی‌های opposite type
KindnessContactReveal       → audit trail نمایش شماره تماس
KindnessListingReport       → گزارش تخلف کاربر
KindnessBookmark            → ذخیره آگهی توسط کاربر
KindnessDuplicateCandidate  → کاندیدای آگهی تکراری برای بررسی ادمین
```

### 6.3 Workflow آگهی

```text
DRAFT
  → submit
PENDING_REVIEW
  → approve → PUBLISHED
  → reject  → REJECTED / NEEDS_EDIT
PUBLISHED
  → close by owner       → CLOSED
  → suspend by admin     → SUSPENDED
  → expire by maintenance → EXPIRED
  → edit sensitive fields → PENDING_REVIEW
```

قواعد مهم:

- ویرایش فیلدهای حساس آگهی منتشرشده، آن را دوباره به review می‌فرستد.
- حذف owner به‌صورت soft-delete انجام می‌شود و audit دارد.
- بستن آگهی با delete فرق دارد و history را حفظ می‌کند.
- تمدید آگهی expired/closed دوباره آن را وارد workflow review می‌کند.

### 6.4 Matching حرفه‌ای

Matching engine از چند سیگنال استفاده می‌کند:

- opposite listing type
- category و parent tree proximity
- province/city proximity
- Persian text normalization
- token overlap
- keyword aliases / synonyms
- score breakdown و reason codes

نتیجه matching به‌صورت materialized در `KindnessMatch` ذخیره می‌شود تا list/detail سریع و قابل audit باشد.

### 6.5 Contact Reveal و Privacy

Public APIs شماره تماس را مخفی نگه می‌دارند. مسیر امن مشاهده شماره:

```text
POST /api/v1/kindness-wall/listings/{slug}/reveal-contact/
```

ویژگی‌ها:

- نیازمند authentication
- throttle مستقل
- ثبت `KindnessContactReveal`
- ثبت audit action
- افزایش counter فقط برای reveal معتبر
- جلوگیری از self-reveal owner
- عدم نمایش مختصات دقیق در public detail

### 6.6 Admin و Analytics

پنل API ادمین شامل موارد زیر است:

- مدیریت دسته‌بندی درختی با جلوگیری از cycle
- approve/reject/suspend/restore آگهی
- review گزارش‌های تخلف
- review کاندیداهای duplicate
- مشاهده matchها و contact revealها
- analytics executive dashboard
- Excel export راست‌به‌چپ برای listings و reports

Analytics شامل:

```text
status distribution
listing type distribution
province/city distribution
category distribution
top viewed listings
top revealed listings
match effectiveness
report distribution
duplicate candidates
```

### 6.7 Kindness Wall Endpoint Summary

Public:

```text
GET  /api/v1/kindness-wall/categories/
GET  /api/v1/kindness-wall/listings/
GET  /api/v1/kindness-wall/listings/{slug}/
GET  /api/v1/kindness-wall/listings/{slug}/matches/
```

Authenticated:

```text
POST   /api/v1/kindness-wall/listings/{slug}/reveal-contact/
POST   /api/v1/kindness-wall/listings/{slug}/report/
POST   /api/v1/kindness-wall/listings/{slug}/bookmark/
DELETE /api/v1/kindness-wall/listings/{slug}/bookmark/
GET    /api/v1/kindness-wall/me/bookmarks/
GET    /api/v1/kindness-wall/me/listings/
POST   /api/v1/kindness-wall/me/listings/
GET    /api/v1/kindness-wall/me/listings/{id}/
PATCH  /api/v1/kindness-wall/me/listings/{id}/
DELETE /api/v1/kindness-wall/me/listings/{id}/
POST   /api/v1/kindness-wall/me/listings/{id}/submit/
POST   /api/v1/kindness-wall/me/listings/{id}/renew/
POST   /api/v1/kindness-wall/me/listings/{id}/close/
GET    /api/v1/kindness-wall/me/matches/
POST   /api/v1/kindness-wall/me/matches/{id}/dismiss/
POST   /api/v1/kindness-wall/me/matches/{id}/contacted/
```

Admin:

```text
GET/POST      /api/v1/kindness-wall/admin/categories/
GET/PATCH/DELETE /api/v1/kindness-wall/admin/categories/{id}/
GET           /api/v1/kindness-wall/admin/listings/
GET           /api/v1/kindness-wall/admin/listings/export/
GET           /api/v1/kindness-wall/admin/listings/{id}/
POST          /api/v1/kindness-wall/admin/listings/{id}/approve/
POST          /api/v1/kindness-wall/admin/listings/{id}/reject/
POST          /api/v1/kindness-wall/admin/listings/{id}/suspend/
POST          /api/v1/kindness-wall/admin/listings/{id}/restore/
GET           /api/v1/kindness-wall/admin/reports/
GET           /api/v1/kindness-wall/admin/reports/export/
POST          /api/v1/kindness-wall/admin/reports/{id}/review/
GET           /api/v1/kindness-wall/admin/matches/
GET           /api/v1/kindness-wall/admin/matches/{id}/
GET           /api/v1/kindness-wall/admin/contact-reveals/
GET           /api/v1/kindness-wall/admin/duplicates/
POST          /api/v1/kindness-wall/admin/duplicates/{id}/review/
GET           /api/v1/kindness-wall/admin/analytics/
```

### 6.8 تست و Performance Contracts

دیوار مهربانی با تست‌های چندلایه پوشش داده شده است:

- domain foundation
- service workflows
- API workflow
- admin/export/analytics
- final edge cases
- privacy regression
- N+1 performance contracts برای serializerهای پرترافیک

---

## 7. Support Desk — میز پشتیبانی

Support Desk یک سامانه تیکت enterprise برای ارتباط ساخت‌یافته کاربر با ادمین سایت است. این اپ به‌عنوان contact form ساده طراحی نشده؛ بلکه یک Help Desk کامل با taxonomy داینامیک، SLA، timeline، internal notes، assignment، canned responses، smart triage، duplicate detection، analytics و export است.

### 7.1 اصول طراحی

```text
Authenticated-only ticketing
Dynamic admin-managed departments
Fully tree-based dynamic categories
Admin-managed ticket types / SLA policies / macros
Service-layer state transitions
Selector-layer optimized reads
Internal notes hidden from users
SLA-aware workflow
Audit for sensitive operations
Excel export and analytics
N+1 performance contracts
```

### 7.2 مدل‌های اصلی

```text
SupportDepartment            → دپارتمان/صف پشتیبانی
SupportCategory              → دسته‌بندی درختی کامل
SupportTicketType            → نوع/علت تیکت داینامیک
SupportSLAPolicy             → سیاست SLA قابل مدیریت
SupportTicket                → تیکت اصلی
SupportTicketMessage         → timeline پیام‌ها و رویدادها
SupportTicketAttachment      → ضمیمه public/internal
SupportCannedResponse        → پاسخ آماده ادمین
SupportTicketAssignment      → تاریخچه ارجاع
SupportTicketStatusHistory   → تاریخچه وضعیت
SupportSLAEvent              → رویدادهای SLA
SupportTicketSatisfaction    → CSAT / رضایت‌سنجی
SupportDuplicateCandidate    → کاندیدای تیکت تکراری
```

### 7.3 Taxonomy داینامیک و درختی

همه taxonomyها توسط ادمین مدیریت می‌شوند. seed پیش‌فرض وجود دارد، اما hard-coded constraint محصولی نیست:

- دپارتمان‌ها
- دسته‌بندی‌های درختی چندسطحی
- نوع تیکت
- SLA policy
- canned response
- tagها

دسته‌بندی‌ها دارای `parent`, `path`, `depth`, `department`, `order`, `is_active` هستند و cycle/self-parent/cross-department parent توسط service layer جلوگیری می‌شود.

### 7.4 Workflow و SLA

```text
DRAFT → SUBMITTED → OPEN / IN_PROGRESS / WAITING_FOR_USER / WAITING_FOR_ADMIN
      → RESOLVED → CLOSED
      → REOPENED
      → ESCALATED
```

SLA از زمان submit اعمال می‌شود:

```text
first_response_due_at
resolution_due_at
sla_breached_at
sla_paused_at
sla_total_paused_seconds
```

وقتی تیکت منتظر پاسخ کاربر است، SLA طبق policy pause می‌شود و با پاسخ کاربر resume می‌شود.

### 7.5 User API Summary

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

### 7.6 Admin API Summary

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

### 7.7 Analytics و Export

داشبورد ادمین شامل توزیع وضعیت، دپارتمان، دسته، نوع تیکت، اولویت، شدت، assignee، CSAT، نرخ reopen، نرخ escalation و نرخ SLA breach است.

خروجی‌های Excel:

```text
tickets
messages
sla
csat
```

همه خروجی‌ها RTL، styled، filterable و audit‌شده هستند.

### 7.8 تست و Performance Contracts

Support Desk دارای تست‌های چندلایه است:

- domain foundation
- service workflows
- user API
- admin API
- analytics/export/tasks
- final performance contracts
- privacy/internal-note regression
- route and permission smoke tests

---

## 8. Observability و Health

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

## 9. Logging و Auditability

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

## 10. Celery و Background Jobs

Celery برای taskهای async و scheduled استفاده می‌شود:

```text
tabyin sync incremental
tabyin sync full
audit log async write
madadkar stale participation expiration
madadkar expired campaign close
LMS certificate PDF task extension point
support SLA breach detection
support stale draft cleanup
support daily digest
```

Queueها:

```text
default
tabyin_sync
madadkar
```

---

## 11. Docker و Production Runtime

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

## 12. نصب و اجرای Local

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

## 13. Quality Gate و CI/CD

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

## 14. OpenAPI Documentation

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

## 15. Production Checklist

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

## 16. فلسفه مهندسی پروژه

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
