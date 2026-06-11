# Support Desk — Full Pro Architecture Blueprint

این سند blueprint رسمی اپ `support_desk` برای پروژه ستاد جنگ است. هدف، ساخت یک «فرم تماس ساده» نیست؛ هدف طراحی و پیاده‌سازی یک سامانه تیکت enterprise، SLA-aware، audit-friendly، extensible، قابل تحلیل، قابل export و مناسب عملیات واقعی پشتیبانی است.

## 1. اصل غیرقابل مذاکره

```text
No MVP shortcut
No fixed hard-coded business taxonomy
No direct DB mutation in views
Service layer owns mutations
Selector layer owns reads
Admin must control operational taxonomy
Tree categories from day one
SLA from day one
Audit from day one
Performance contracts before finalization
```

همه taxonomyهای عملیاتی باید ادمین‌محور باشند. سیستم می‌تواند seed پیش‌فرض حرفه‌ای داشته باشد، اما ادمین باید بتواند همه آن‌ها را مدیریت کند.

## 2. Taxonomy Strategy — کاملاً حرفه‌ای و داینامیک

### 2.1 Department — دپارتمان‌های قابل مدیریت

دپارتمان‌ها کاملاً dynamic هستند و توسط ادمین ایجاد/ویرایش/غیرفعال/مرتب‌سازی می‌شوند.

Seed پیش‌فرض پیشنهادی:

```text
پشتیبانی عمومی
فنی
مالی و پرداخت
حساب کاربری و احراز هویت
آموزش / LMS
دیوار مهربانی
مددکار
گزارشات مردمی
تبیین محتوا
امنیت و حریم خصوصی
همکاری و مشارکت
```

اما هیچ‌کدام hard-coded business logic نخواهند بود. فقط data seed هستند.

### 2.2 Tree Category — دسته‌بندی درختی کامل

Category حتماً tree-based است:

```text
SupportCategory
  parent -> self
  department -> SupportDepartment
  title
  slug
  path
  depth
  order
  is_active
  tickets_count
  open_tickets_count
```

ادمین باید بتواند:

- root category بسازد.
- subcategory چندسطحی بسازد.
- category را جابه‌جا کند.
- cycle/self-parent را سیستم جلوگیری کند.
- category را soft-delete/deactivate کند.
- category دارای ticket فعال را حذف امن نکند، مگر با سیاست مشخص.
- category را restore کند.

Seed درختی پیشنهادی:

```text
حساب کاربری
  ورود و رمز عبور
  OTP و شماره موبایل
  تغییر اطلاعات پروفایل
  مشکل احراز هویت

پرداخت و مالی
  پرداخت ناموفق
  پرداخت موفق ولی ثبت‌نشده
  رسید و پیگیری پرداخت
  مغایرت مبلغ
  بازگشت وجه

مشکلات فنی
  خطای سایت
  خطای API یا اپلیکیشن
  کندی یا قطعی
  مشکل آپلود فایل
  مشکل نمایش صفحه

LMS / آموزش
  ثبت‌نام در دوره
  مشاهده درس‌ها
  آزمون و تلاش مجدد
  مدرک و اعتبارسنجی
  پیشرفت دوره

دیوار مهربانی
  ثبت آگهی
  تأیید یا رد آگهی
  مشکل شماره تماس
  گزارش آگهی
  مچینگ و پیشنهادها

مددکار
  کمپین‌ها
  مشارکت و سهم
  پرداخت مددکار
  رسید پرداخت

گزارشات مردمی
  ثبت گزارش
  پیگیری وضعیت گزارش
  ضمیمه گزارش

تبیین محتوا
  ارسال محتوا
  مشکل محتوای منتشرشده
  درخواست اصلاح محتوا

امنیت و حریم خصوصی
  گزارش آسیب‌پذیری
  سوءاستفاده یا جعل هویت
  درخواست حذف/اصلاح داده

پیشنهاد و همکاری
  پیشنهاد محصولی
  همکاری رسانه‌ای
  همکاری فنی
  سایر
```

### 2.3 Ticket Type / Reason — داینامیک، نه hard-coded

به‌جای اینکه فقط enum ثابت داشته باشیم، مدل `SupportTicketType` می‌گذاریم:

```text
SupportTicketType
  code
  title
  description
  default_department
  default_priority
  default_severity
  default_sla_policy
  order
  is_active
```

Seed پیشنهادی:

```text
QUESTION           سؤال عمومی
TECHNICAL_ISSUE    مشکل فنی
ACCOUNT            حساب کاربری
PAYMENT            پرداخت و مالی
REPORT             گزارش خطا یا تخلف
SUGGESTION         پیشنهاد
PARTNERSHIP        همکاری
SECURITY           امنیت و حریم خصوصی
OTHER              سایر
```

این‌ها داده seed هستند، نه constraint تغییرناپذیر. ادمین می‌تواند اضافه/ویرایش/غیرفعال کند.

### 2.4 Priority و Severity — policy-driven

Priority و Severity می‌توانند enum فنی برای stability داخلی داشته باشند، اما mapping عملیاتی و SLA از طریق `SupportSLAPolicy` و admin config کنترل می‌شود.

Priority seed:

```text
low
normal
high
urgent
```

Severity seed:

```text
minor
major
critical
blocker
```

## 3. Core Domain Models

### 3.1 SupportDepartment

مدیریت queue و routing:

```text
id
uuid
title
slug
description
default_assignee
order
is_active
created_at
updated_at
```

### 3.2 SupportCategory

دسته‌بندی درختی کامل:

```text
id
parent
department
title
slug
path
depth
description
icon
order
tickets_count
open_tickets_count
is_active
created_at
updated_at
```

### 3.3 SupportTicketType

نوع/علت تیکت قابل مدیریت:

```text
id
code
title
description
default_department
default_category
default_priority
default_severity
default_sla_policy
order
is_active
created_at
updated_at
```

### 3.4 SupportSLAPolicy

SLA policy قابل مدیریت توسط ادمین:

```text
id
title
slug
department
ticket_type
priority
severity
first_response_minutes
resolution_minutes
business_hours_only
pause_when_waiting_for_user
escalate_on_breach
is_active
created_at
updated_at
```

Seed پیشنهادی:

```text
Normal Support: first response 24h, resolution 72h
High Priority: first response 8h, resolution 24h
Urgent/Critical: first response 2h, resolution 8h
Payment Issue: first response 4h, resolution 24h
Security Issue: first response 1h, resolution 8h
```

### 3.5 SupportTicket

رکورد اصلی تیکت:

```text
id
uuid
ticket_number
owner
department
category
ticket_type
subject
description_snapshot
status
priority
severity
channel
assigned_to
submitted_at
first_admin_response_at
last_user_message_at
last_admin_message_at
last_activity_at
resolved_at
closed_at
reopened_at
escalated_at
escalated_by
escalation_reason
first_response_due_at
resolution_due_at
sla_breached_at
sla_paused_at
sla_total_paused_seconds
message_count
attachment_count
internal_note_count
reopen_count
satisfaction_rating_snapshot
search_document
is_active
created_at
updated_at
```

Ticket number format پیشنهادی:

```text
SUP-YYYYMM-SEQ-RAND
مثال: SUP-202606-0042-X7K9
```

### 3.6 SupportTicketMessage

Thread و timeline:

```text
id
ticket
author
message_type
body
is_internal
is_from_staff
created_at
edited_at
deleted_at
metadata
```

Message types:

```text
USER_MESSAGE
ADMIN_REPLY
INTERNAL_NOTE
SYSTEM_EVENT
STATUS_CHANGE
ASSIGNMENT_CHANGE
SLA_EVENT
```

کاربر فقط پیام‌های غیر internal را می‌بیند.

### 3.7 SupportTicketAttachment

```text
id
ticket
message
uploaded_by
file
original_filename
content_type
file_size
attachment_kind
visibility
created_at
```

Visibility:

```text
public
internal_only
```

### 3.8 SupportTag / SupportTicketTag

```text
SupportTag:
  name
  slug
  normalized_name
  usage_count

SupportTicketTag:
  ticket
  tag
  source
```

### 3.9 SupportCannedResponse

پاسخ آماده داینامیک:

```text
id
department
category
title
body
is_active
usage_count
created_at
updated_at
```

Seed پیشنهادی:

```text
درخواست اطلاعات بیشتر
پیگیری پرداخت
ارجاع به تیم فنی
حل مشکل و درخواست تأیید کاربر
راهنمای بازیابی حساب
```

### 3.10 History / Audit Companion Models

```text
SupportTicketAssignment
SupportTicketStatusHistory
SupportSLAEvent
SupportTicketSatisfaction
SupportDuplicateCandidate
```

## 4. Ticket Lifecycle

```text
DRAFT
  → SUBMITTED
SUBMITTED
  → OPEN
OPEN
  → IN_PROGRESS
  → WAITING_FOR_USER
  → WAITING_FOR_ADMIN
  → RESOLVED
  → CLOSED
  → ESCALATED
RESOLVED
  → REOPENED
  → CLOSED
CLOSED
  → REOPENED فقط تا reopen window
```

Statuses:

```text
draft
submitted
open
in_progress
waiting_for_user
waiting_for_admin
resolved
closed
reopened
escalated
spam
archived
```

## 5. SLA Engine

SLA از روز اول وجود دارد.

محاسبه‌ها:

```text
first_response_due_at
resolution_due_at
sla_breached_at
sla_paused_at
sla_total_paused_seconds
```

قواعد:

- هنگام submit، policy resolve می‌شود.
- وقتی منتظر کاربر است، SLA pause می‌شود.
- وقتی کاربر reply می‌دهد، SLA resume می‌شود.
- Celery task breachها را علامت می‌زند.
- breach می‌تواند escalation ایجاد کند.

## 6. Smart Triage

Smart suggestion endpoint:

```text
POST /api/v1/support/me/tickets/suggest/
```

خروجی:

```text
suggested_department
suggested_category
suggested_ticket_type
suggested_priority
suggested_severity
suggested_sla_policy
similar_tickets
duplicate_warning
suggested_canned_help
```

الگوریتم اولیه:

- Persian normalization
- token overlap
- category tree proximity
- department/type similarity
- same-user recent open tickets
- keyword aliases

## 7. Permissions

### User

- create draft ticket
- submit own ticket
- view own tickets
- reply to own open/resolved-reopenable tickets
- upload public attachments
- reopen within policy
- submit satisfaction rating

### Admin

- view all tickets
- manage departments/categories/types/SLA policies/canned responses
- assign tickets
- change status
- reply
- internal notes
- escalate
- close
- export
- analytics
- duplicate review

## 8. API Contract

### Public/Auth user

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
POST   /api/v1/support/me/tickets/{ticket_number}/attachments/
POST   /api/v1/support/me/tickets/{ticket_number}/reopen/
POST   /api/v1/support/me/tickets/{ticket_number}/satisfaction/
GET    /api/v1/support/me/tickets/{ticket_number}/timeline/
```

### Admin

```text
GET/POST       /api/v1/support/admin/departments/
GET/PATCH      /api/v1/support/admin/departments/{id}/
GET/POST       /api/v1/support/admin/categories/
GET/PATCH      /api/v1/support/admin/categories/{id}/
GET/POST       /api/v1/support/admin/ticket-types/
GET/PATCH      /api/v1/support/admin/ticket-types/{id}/
GET/POST       /api/v1/support/admin/sla-policies/
GET/PATCH      /api/v1/support/admin/sla-policies/{id}/
GET/POST       /api/v1/support/admin/canned-responses/
GET/PATCH      /api/v1/support/admin/canned-responses/{id}/
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
```

## 9. Analytics

```text
total tickets
open tickets
unassigned tickets
overdue tickets
sla breached tickets
avg first response time
avg resolution time
tickets by status
tickets by department
tickets by category tree
tickets by type
tickets by priority
tickets by severity
tickets by assignee
top users by ticket count
CSAT average
CSAT distribution
reopen rate
escalation rate
admin workload
first response SLA compliance
resolution SLA compliance
```

## 10. Export

Excel export:

```text
tickets
messages
sla breaches
admin workload
csat ratings
```

ویژگی‌ها:

- RTL workbook
- styled headers
- filters
- summary sheet
- date range
- department/category/status/assignee filters

## 11. Audit Actions

```text
SUPPORT_DEPARTMENT_CREATED
SUPPORT_DEPARTMENT_UPDATED
SUPPORT_DEPARTMENT_DEACTIVATED
SUPPORT_CATEGORY_CREATED
SUPPORT_CATEGORY_UPDATED
SUPPORT_CATEGORY_DEACTIVATED
SUPPORT_TICKET_TYPE_CREATED
SUPPORT_TICKET_TYPE_UPDATED
SUPPORT_SLA_POLICY_CREATED
SUPPORT_SLA_POLICY_UPDATED
SUPPORT_TICKET_CREATED
SUPPORT_TICKET_SUBMITTED
SUPPORT_TICKET_UPDATED
SUPPORT_TICKET_ASSIGNED
SUPPORT_TICKET_REPLIED
SUPPORT_TICKET_INTERNAL_NOTE_ADDED
SUPPORT_TICKET_STATUS_CHANGED
SUPPORT_TICKET_RESOLVED
SUPPORT_TICKET_CLOSED
SUPPORT_TICKET_REOPENED
SUPPORT_TICKET_ESCALATED
SUPPORT_ATTACHMENT_ADDED
SUPPORT_SATISFACTION_SUBMITTED
SUPPORT_CANNED_RESPONSE_CREATED
SUPPORT_CANNED_RESPONSE_USED
SUPPORT_EXPORT_GENERATED
SUPPORT_DUPLICATE_REVIEWED
SUPPORT_SLA_BREACHED
```

## 12. Throttling

```text
support_ticket_create: 5/hour
support_ticket_message: 30/hour
support_attachment_upload: 20/hour
support_suggest: 20/hour
support_user_browse: 120/min
support_admin_actions: 120/min
```

## 13. Phase Plan

```text
Support Phase 0 — Full Pro Architecture Blueprint               ✅ Done
Support Phase 1 — Domain Foundation + Seeds                     ✅ Done
Support Phase 2 — Service Layer + Workflow/SLA/Triage           ✅ Done
Support Phase 3 — User API + Timeline + Attachments             ✅ Done
Support Phase 4 — Admin API + Taxonomy + Assignment + Macros     ✅ Done
Support Phase 5 — Analytics + Export + SLA Tasks                ✅ Done
Support Phase 6 — Full Tests + Performance + Documentation      ✅ Done
```

## 14. Final Non-Negotiable Implementation Notes

- Categories are tree-based from day one.
- Departments, categories, ticket types, SLA policies, canned responses and tags are admin-managed.
- Seed data must be defaults only, never hard-coded product constraints.
- All sensitive actions must create audit logs.
- Views orchestrate only.
- Services own state transitions.
- Selectors own optimized reads.
- Public/user serializers must not leak internal notes.
- Admin serializers can expose operational metadata.
- Every phase requires targeted tests and final `make verify` before push.
