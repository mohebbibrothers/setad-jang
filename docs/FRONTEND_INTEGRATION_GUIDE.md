# راهنمای اتصال Frontend به Backend ستاد جنگ

این سند برای frontend developer نوشته شده تا بعد از deploy یا در محیط local بتواند بدون حدس‌زدن، از Swagger/OpenAPI و قراردادهای API استفاده کند.

---

## 1. آدرس‌های اصلی

در local development:

```text
Backend base URL: http://127.0.0.1:8000
Swagger UI     : http://127.0.0.1:8000/api/docs/
ReDoc          : http://127.0.0.1:8000/api/redoc/
OpenAPI schema : http://127.0.0.1:8000/api/schema/
Health         : http://127.0.0.1:8000/api/v1/health/
Readiness      : http://127.0.0.1:8000/api/v1/health/ready/
Metrics        : http://127.0.0.1:8000/api/v1/metrics/
```

در production، فقط دامنه را جایگزین کن:

```text
https://api.example.com/api/docs/
https://api.example.com/api/schema/
```

---

## 2. قرارداد نسخه‌بندی API

همه endpointهای product زیر این prefix هستند:

```text
/api/v1/
```

نمونه:

```text
/api/v1/auth/login/password/
/api/v1/madadkar/campaigns/
/api/v1/support/me/tickets/
```

---

## 3. قرارداد Response Envelope

### موفق

```json
{
  "success": true,
  "status_code": 200,
  "message": "عملیات با موفقیت انجام شد.",
  "data": {}
}
```

### خطا

```json
{
  "success": false,
  "status_code": 400,
  "message": "درخواست نامعتبر است.",
  "errors": {}
}
```

Frontend نباید مستقیماً فرض کند payload همیشه root object است؛ داده اصلی در `data` قرار می‌گیرد.

### حذف (DELETE) — عمداً 200 برمی‌گرداند، نه 204

این مورد یک انحراف آگاهانه از قرارداد رایج REST است و باید در frontend
صریحاً در نظر گرفته شود.

عملیات حذف — چه soft-delete و چه hard-delete — همیشه **HTTP 200** با همان
envelope استاندارد برمی‌گرداند و `data` برابر `null` است:

```json
{
  "success": true,
  "status_code": 200,
  "message": "با موفقیت حذف شد.",
  "data": null
}
```

**چرا 204 نه؟** طبق RFC، پاسخ 204 اصلاً نباید body داشته باشد. اگر حذف را
204 می‌کردیم، تنها endpointهای پروژه می‌شدند که envelope ندارند و frontend
مجبور می‌شد فقط برای DELETE یک مسیر جداگانه در لایهٔ HTTP نگه دارد.
مهم‌تر اینکه پیام فارسی قابل نمایش به کاربر («سفارش شما حذف شد») جایی برای
رفتن نداشت.

**پیامد عملی برای frontend:**

- برای DELETE هم مثل بقیهٔ درخواست‌ها `response.json()` را بخوانید؛ body
  همیشه وجود دارد. کدی مثل `if (res.status === 204) return null` هرگز
  اجرا نمی‌شود.
- `data` برای حذف همیشه `null` است — به آن دست نزنید.
- موفقیت را با `success === true` بسنجید، نه با تطبیق کد وضعیت.
- `message` را مستقیماً به کاربر نشان دهید؛ متن فارسی و آمادهٔ نمایش است.

---

## 4. احراز هویت و JWT

Backend از JWT استفاده می‌کند.

### Login با password

```http
POST /api/v1/auth/login/password/
Content-Type: application/json
```

نمونه body:

```jsonc
{
  "identifier": "user@example.com",
  "password": "<user-password>" // pragma: allowlist secret
}
```

پاسخ شامل token است. در requestهای بعدی:

```http
Authorization: Bearer <access_token>
```

### Refresh token

```http
POST /api/v1/auth/token/refresh/
```

### Logout

```http
POST /api/v1/auth/logout/
```

### اطلاعات کاربر

```http
GET /api/v1/auth/me/
PATCH /api/v1/auth/me/
GET /api/v1/auth/profile/
PATCH /api/v1/auth/profile/
```

---

## 5. OTP و Signup

Signup جدید:

```text
POST /api/v1/auth/signup/request/
POST /api/v1/auth/signup/verify/
```

Login با OTP:

```text
POST /api/v1/auth/login/otp/request/
POST /api/v1/auth/login/otp/verify/
```

نکته UI:

```text
پیام‌های خطا برای جلوگیری از enumeration عمداً همیشه جزئیات وجود/عدم وجود حساب را افشا نمی‌کنند.
```

---

## 6. Pagination

لیست‌های paginated داخل `data` چنین ساختاری دارند:

```json
{
  "success": true,
  "status_code": 200,
  "message": "...",
  "data": {
    "count": 120,
    "next": "...",
    "previous": null,
    "results": []
  }
}
```

پارامترهای رایج:

```text
?page=1&page_size=20
```

---

## 7. File Upload / multipart

برای endpointهای دارای فایل از `multipart/form-data` استفاده کن.

دامنه‌هایی که upload دارند:

```text
Public Reports attachments
R4J report/criminal evidence attachments
Madadkar campaign images
LMS media
Kindness Wall images
Support ticket attachments
```

نکته: بعضی فیلدهای list/dict در multipart ممکن است JSON string باشند. قرارداد دقیق هر endpoint در Swagger مشخص است.

---

## 8. CORS و اتصال Frontend

در production باید دامنه frontend در env ثبت شود:

```env
CORS_ALLOWED_ORIGINS=https://example.com,https://www.example.com
CSRF_TRUSTED_ORIGINS=https://example.com,https://www.example.com
ALLOWED_HOSTS=api.example.com
```

اگر frontend روی localhost است:

```env
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```

---

## 9. Endpointهای مهم برای شروع Frontend

### Auth

```text
POST /api/v1/auth/signup/request/
POST /api/v1/auth/signup/verify/
POST /api/v1/auth/login/password/
POST /api/v1/auth/token/refresh/
GET  /api/v1/auth/me/
GET  /api/v1/auth/sessions/
```

### Madadkar

```text
GET  /api/v1/madadkar/campaigns/
GET  /api/v1/madadkar/campaigns/{slug}/
POST /api/v1/madadkar/campaigns/{slug}/participate/
GET  /api/v1/madadkar/payment/verify/
POST /api/v1/madadkar/payment/verify/
GET  /api/v1/madadkar/me/participations/
GET  /api/v1/madadkar/me/receipts/
POST /api/v1/madadkar/receipts/verify/
GET  /api/v1/madadkar/campaigns/{slug}/transparency/
```

### Support Desk

```text
GET,POST /api/v1/support/me/tickets/
GET,PATCH /api/v1/support/me/tickets/{ticket_number}/
POST /api/v1/support/me/tickets/{ticket_number}/submit/
POST /api/v1/support/me/tickets/{ticket_number}/reply/
POST /api/v1/support/me/tickets/{ticket_number}/attachments/
GET /api/v1/support/me/tickets/{ticket_number}/timeline/
GET /api/v1/support/knowledge/articles/
```

### R4J

```text
GET  /api/v1/r4j/criminals/
GET  /api/v1/r4j/criminals/{lookup}/
POST /api/v1/r4j/criminals/{criminal_id}/reports/
POST /api/v1/r4j/criminals/{criminal_id}/bounty/
GET  /api/v1/r4j/me/reports/
GET  /api/v1/r4j/me/bounties/
```

### LMS

```text
GET /api/v1/lms/courses/
GET /api/v1/lms/courses/{slug}/
POST /api/v1/lms/courses/{slug}/enroll/
GET /api/v1/lms/courses/{slug}/lessons/
POST /api/v1/lms/lessons/{lesson_id}/progress/
GET /api/v1/lms/me/recommendations/
```

### Kindness Wall

```text
GET /api/v1/kindness-wall/listings/
GET /api/v1/kindness-wall/listings/{slug}/
GET,POST /api/v1/kindness-wall/me/listings/
POST /api/v1/kindness-wall/me/listings/{listing_id}/submit/
POST /api/v1/kindness-wall/listings/{slug}/reveal-contact/
```

### Tabyin

```text
GET /api/v1/tabyin/contents/
GET /api/v1/tabyin/contents/{external_id}/
GET,POST /api/v1/tabyin/me/submissions/
```

---

## 10. Swagger برای frontend developer

پیشنهاد workflow:

```text
1. Backend را بالا بیاور.
2. /api/docs/ را باز کن.
3. ابتدا auth login را تست کن.
4. Authorize را در Swagger با Bearer token تنظیم کن.
5. endpointهای user-facing هر app را تست کن.
6. اگر schema تغییر کرد، از /api/schema/ خروجی جدید بگیر.
```

---

## 11. نکات مهم UI/UX در برخورد با API

- روی `status_code` داخل body به‌تنهایی تکیه نکن؛ HTTP status هم مهم است.
- خطاهای serializer ممکن است در `errors` به‌شکل object برگردند.
- برای عملیات مالی Madadkar، بعد از `participate` کاربر باید به `gateway_url` هدایت شود.
  در حالت درگاه واقعی، پاسخ participate شامل `gateway_url` و `authority` است؛ بعد از
  بازگشت درگاه، فرانت روی `GET /api/v1/madadkar/payment/verify/?authority=...&status=...`
  نتیجه را می‌خواند و صفحه وضعیت پرداخت را از همان envelope JSON رندر می‌کند
  (redirect خودکار به SPA وجود ندارد). همه مبالغ در این API به تومان‌اند.
- برای Support Desk، ticket ابتدا draft است و سپس submit می‌شود.
- برای R4J، public visibility فیلدها ممکن است بعضی اطلاعات را `null` کند.
- برای uploadها progress UI و error handling فایل لازم است.
- برای 401، refresh token flow یا redirect به login را اجرا کن.
- برای 429، پیام rate-limit و retry بعداً نمایش بده.

---

## 12. Pre-deploy checklist مخصوص اتصال Frontend

```text
Swagger باز می‌شود؟
/api/schema/ بدون خطا خروجی می‌دهد؟
CORS_ALLOWED_ORIGINS شامل دامنه frontend است؟
ALLOWED_HOSTS شامل دامنه API است؟
JWT login در Swagger کار می‌کند؟
endpointهای public بدون token کار می‌کنند؟
endpointهای protected بدون token 401 می‌دهند؟
فایل upload در multipart تست شده؟
Madadkar payment flow هم در sandbox و هم zarinpal تست شده؟ (participate→درگاه→verify→رسید، مبالغ تومان)
Support ticket create/submit/reply تست شده؟
```
