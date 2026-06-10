# ستاد جنگ — Backend

Backend پروژه‌ی **ستاد جنگ**، ساخته‌شده با **Django 6 + DRF + Celery + Redis**.

این پروژه شامل یک سیستم احراز هویت چندشناسه‌ای (multi-identifier)، گزارشات مردمی و یک ingestion engine کامل برای محتوای جهاد تبیین است.

---

## ✨ ویژگی‌های کلیدی

### 🔐 احراز هویت چندشناسه‌ای (Multi-Identifier Auth)
- **ثبت‌نام با ایمیل یا شماره موبایل** — بدون ساخت حساب تا قبل از تأیید OTP
- **ورود با رمز عبور** (identifier-aware) یا **کد یکبارمصرف**
- **مدیریت شناسه ثانویه** — اتصال، تأیید و تغییر شناسه اصلی
- **Provider Pattern** برای delivery — آماده برای تعویض SMS/Email vendor بدون تغییر business logic
- **ACID-safe OTP delivery** — اگر ارسال fail شود، کل تراکنش rollback می‌شود
- **Anti-abuse layers** — honeypot detection، Redis-backed global anomaly guard، constant-time responses
- **Timing-attack mitigation** — dummy hash path در authentication backend

### 📦 API استاندارد
- **Response envelope یکپارچه** (`success / status_code / message / data`)
- **JWT Authentication** با rotation و blacklist
- **OpenAPI / Swagger** کامل با تگ‌های فارسی و enum های stable
- **Backward-compatible API evolution** — legacy v1 endpoints با deprecation headers فعال هستند

### ⚙️ زیرساخت
- **Celery + Beat + Flower** برای جاب‌های زمان‌بندی‌شده و monitoring
- **Redis** برای cache، broker و global anomaly guard
- **Caching هوشمند** سطح selector با namespace versioning و invalidation خودکار
- **Hierarchical logging** با Request ID middleware
- **Dockerized** با orchestration کامل (web + worker + beat + flower + redis)

### 🔄 Tabyin Ingestion Engine
- Sync کامل و افزایشی از منبع خارجی
- Bulk operations برای حداقل query
- Change detection با SHA-256 content hashing
- Soft delete برای محتوای حذف‌شده در منبع
- Async dispatch توسط ادمین + endpoint پیگیری وضعیت task

### 🧪 کیفیت کد
- **226 تست** با pytest + factory-boy
- **0 warning** در test pipeline
- **Ruff** برای lint
- **Type hints** در سراسر پروژه

---

## 🧱 معماری در یک نگاه

```text
                       ┌────────────────────────┐
                       │     Frontend / SPA     │
                       └────────────┬───────────┘
                                    │ HTTPS / JSON
                                    ▼
        ┌────────────────────────────────────────────────────┐
        │                Django + DRF (web)                  │
        │  ─────────────────────────────────────────────     │
        │   - Multi-Identifier Auth (v2) + Legacy Auth (v1)  │
        │   - Public Reports, Tabyin Ingestion Engine        │
        │   - Service / Selector layers (HackSoft style)     │
        │   - Standard response envelope                     │
        │   - Request-ID middleware                          │
        └─────────────┬──────────────────────────────────┬───┘
                      │                                  │
                      ▼                                  ▼
          ┌──────────────────────┐         ┌──────────────────────────┐
          │       Redis          │         │   Celery Worker / Beat   │
          │  cache + broker      │◀───────▶│  async sync, scheduling │
          │  + OTP guard         │         └──────────────────────────┘
          └──────────────────────┘                      │
                                                        ▼
                                              ┌──────────────────┐
                                              │  Mohtavanegar    │
                                              │  (external API)  │
                                              └──────────────────┘