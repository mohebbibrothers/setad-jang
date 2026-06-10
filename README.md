# ستاد جنگ — Enterprise Django REST Backend

Backend پروژه‌ی **ستاد جنگ** با **Django 6 + Django REST Framework + Celery + Redis + PostgreSQL**.

هدف پروژه ساخت یک backend رزومه‌محور، production-minded و قابل توسعه است که چند دامنه‌ی مستقل را با معماری تمیز، تست گسترده، response envelope یکپارچه، audit logging و مستندات OpenAPI پوشش می‌دهد.

---

## ✨ ماژول‌ها

- **Core** — BaseModel، soft delete managers، response envelope، pagination، exception handler، health checks، request-id logging، cache helpers.
- **Authentication** — Custom User، احراز هویت چندشناسه‌ای email/phone، OTP هش‌شده، JWT rotation/blacklist، anti-abuse، provider pattern برای delivery.
- **Public Reports** — گزارشات مردمی، موضوعات قابل مدیریت، attachment upload، public/admin API.
- **Tabyin** — ingestion engine محتوای تبیین با provider pattern، HTTP retry/backoff، hashing، bulk sync، Celery tasks و cache-aware selectors.
- **Audit Logs** — ثبت لاگ فعالیت‌ها با action constants، metadata extraction و async dispatch.
- **R4J** — Reward for Justice: پروفایل مجرم، گزارش community، field-level approval، bounty state machine، concurrency-safe counters.
- **Madadkar** — charitable crowdfunding: sponsor/campaign/participation/payment، share reservation، Zarinpal/Sandbox provider pattern، Excel export و admin analytics.

---

## 🧱 معماری

```text
Frontend / Client
      │
      ▼
Django + DRF API
      │
      ├── Service Layer      → تمام mutationها، transaction safety، business rules
      ├── Selector Layer     → query optimization، select_related/prefetch_related، cache-aware reads
      ├── Serializer Layer   → I/O validation و schema-friendly contracts
      ├── Audit Layer        → async activity logging
      └── Celery Tasks       → sync jobs، maintenance، async audit

Redis      → cache + broker + OTP anomaly guard
PostgreSQL → production database
OpenAPI    → Swagger/ReDoc via drf-spectacular
```

اصول ثابت پروژه:

- Viewها business logic ندارند و به services/selectors delegate می‌کنند.
- پاسخ APIها در envelope استاندارد برمی‌گردد.
- mutationهای حساس با `transaction.atomic` و در صورت نیاز `select_for_update` امن می‌شوند.
- تمام endpointهای حساس permission، throttling، logging و audit مناسب دارند.
- warning در test pipeline مجاز نیست.

---

## 🔐 امنیت و احراز هویت

- ثبت‌نام و ورود با email یا phone.
- OTP در DB به‌صورت SHA-256 hash ذخیره می‌شود، نه plain code.
- replay protection با `is_used=True` بعد از verify.
- محدودیت تلاش برای OTP و throttling چندلایه.
- honeypot و global OTP anomaly guard.
- JWT access/refresh با rotation و blacklist.
- backend اختصاصی `MultiIdentifierBackend` برای login با شناسه‌های مختلف.

---

## 💳 پرداخت مددکار

مددکار از provider pattern استفاده می‌کند:

- `SandboxProvider` برای development/test.
- `ZarinpalProvider` برای اتصال HTTP واقعی به زرین‌پال.

ویژگی‌های payment flow:

- رزرو سهم با lock روی campaign row.
- verify خارج از transaction طولانی برای جلوگیری از نگه‌داشتن connection هنگام I/O.
- idempotency برای double verify.
- تشخیص amount tampering.
- expire کردن مشارکت‌های stale با Celery.
- sync counters مبتنی بر source-of-truth.

---

## ⚙️ زیرساخت عملیاتی

Docker Compose شامل:

- `web` — Django/Gunicorn
- `postgres` — PostgreSQL production database
- `redis` — cache + broker
- `worker` — Celery worker با queueهای `default,tabyin_sync,madadkar`
- `beat` — Celery Beat
- `flower` — monitoring

Production settings به‌صورت پیش‌فرض PostgreSQL می‌خواهد. SQLite فقط برای development و demo/emergency با opt-in صریح مجاز است.

---

## 🧪 کیفیت و تست

وضعیت فعلی verification:

```bash
ruff check .                                      # All checks passed
python manage.py check                           # System check identified no issues
python manage.py makemigrations --check --dry-run # No changes detected
python manage.py spectacular --file schema.yaml --validate
pytest -q                                        # 783 passed
```

تست‌ها پوشش می‌دهند:

- happy path و failure path
- validation boundaries
- permissions و IDOR
- state machines
- audit dispatch
- counter sync
- concurrency-sensitive flows
- payment idempotency و gateway errors
- file upload با فایل معتبر تولیدشده توسط Pillow
- operational hardening برای production settings و docker-compose

---

## 🚀 اجرای local بدون Docker

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
python manage.py migrate
python manage.py runserver
```

Celery در محیط local:

```bash
celery -A config worker -l info -Q default,tabyin_sync,madadkar
celery -A config beat -l info
```

---

## 🐳 اجرای Docker

ابتدا `.env.example` را به `.env` کپی کن و حداقل این مقدارها را امن تنظیم کن:

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

## 📚 مستندات API

بعد از اجرای سرور:

- Swagger UI: `/api/docs/`
- ReDoc: `/api/redoc/`
- OpenAPI schema: `/api/schema/`
- Health: `/api/v1/health/`
- Detailed health: `/api/v1/health/detailed/`

---

## 🛡️ Production checklist کوتاه

- `SECRET_KEY` و `JWT_SIGNING_KEY` قوی و جداگانه.
- `DEBUG=False`.
- `ALLOWED_HOSTS` دقیق.
- PostgreSQL واقعی با backup policy.
- Redis پایدار برای cache/broker.
- HTTPS پشت reverse proxy.
- `SECURE_SSL_REDIRECT=True` در production واقعی.
- CORS محدود به دامنه‌های frontend.
- اجرای worker با queueهای `default,tabyin_sync,madadkar`.
- monitoring برای Celery/Flower/logs.
