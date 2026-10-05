# Environment Matrix — Setad Jang Production Operations

این سند تفاوت environmentهای پروژه را مشخص می‌کند تا هیچ تنظیم production به‌صورت حدسی انجام نشود.

## 1. Environments

| Environment | هدف | Settings module | Database | Cache/Broker | External Providers |
|---|---|---|---|---|---|
| local | توسعه روزمره | `config.settings.development` | SQLite یا Postgres local | locmem یا Redis local | console/sandbox |
| staging | تست قبل از production | `config.settings.production` | PostgreSQL staging | Redis staging | sandbox/test credentials |
| production | سرویس واقعی | `config.settings.production` | PostgreSQL managed | Redis managed | real credentials |

## 2. Required production env

```env
DJANGO_SETTINGS_MODULE=config.settings.production
DEBUG=False
SECRET_KEY=<strong-secret>
JWT_SIGNING_KEY=<separate-strong-secret>
ALLOWED_HOSTS=example.com,www.example.com
CORS_ALLOWED_ORIGINS=https://example.com,https://www.example.com
DATABASE_ENGINE=postgres
POSTGRES_DB=setadjang
POSTGRES_USER=setadjang
POSTGRES_PASSWORD=<strong-password>
POSTGRES_HOST=<postgres-host>
POSTGRES_PORT=5432
CACHE_BACKEND=redis
REDIS_URL=redis://<redis-host>:6379/1
CELERY_BROKER_URL=redis://<redis-host>:6379/2
CELERY_RESULT_BACKEND=redis://<redis-host>:6379/2
LOG_FORMAT=json
PROMETHEUS_METRICS_ENABLED=True
SECURE_SSL_REDIRECT=False
SECURE_HSTS_SECONDS=31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS=True
SECURE_HSTS_PRELOAD=True
```

## 3. Media and CDN

```env
MEDIA_STORAGE_BACKEND=s3
FILE_SCAN_PROVIDER=extension_blocklist
AWS_ACCESS_KEY_ID=<access-key>
AWS_SECRET_ACCESS_KEY=<secret-key>
AWS_STORAGE_BUCKET_NAME=<bucket>
AWS_S3_REGION_NAME=<region>
AWS_S3_ENDPOINT_URL=<optional-minio-endpoint>
AWS_S3_CUSTOM_DOMAIN=<cdn-domain>
```

## 4. Email/SMS/Payment readiness

### Email — Gmail SMTP (default; no phone/card, Iran-friendly)

رایگان ۵۰۰/روز. اعتبارنامه: آدرس کامل جیمیل + App Password (نیازمند
2-Step Verification؛ ساخت از `myaccount.google.com/apppasswords`).
`DEFAULT_FROM_EMAIL` باید همان جیمیل فرستنده باشد (Gmail From متناقض را override
می‌کند). برای ESP حرفه‌ای‌تر (Resend/Mailjet) فقط host/user/pass عوض می‌شود؛
دقت کنید اکثر ESPهای خارجی ثبت‌نام با شمارهٔ موبایل ایران را رد می‌کنند.

```env
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=<gmail-account>
EMAIL_HOST_PASSWORD=<app-password-16>
DEFAULT_FROM_EMAIL=<gmail-account>
```

### SMS — after license

```env
OTP_PROVIDER=sms
OTP_SMS_PROVIDER=http
SMS_API_URL=<licensed-provider-url>
SMS_API_KEY=<api-key>
SMS_SENDER=<approved-sender>
SMS_TIMEOUT_SECONDS=10
```

### Zarinpal — after license

```env
MADADKAR_PAYMENT_PROVIDER=zarinpal
MADADKAR_ZARINPAL_MERCHANT_ID=<merchant-id>
MADADKAR_ZARINPAL_SANDBOX=False
MADADKAR_PAYMENT_CALLBACK_BASE_URL=https://example.com
```

## 5. Readiness checks

Before considering production ready:

```bash
make verify
python manage.py check --deploy --settings=config.settings.production
curl https://example.com/api/v1/health/ready/
curl https://example.com/api/v1/health/detailed/
curl https://example.com/api/v1/metrics/
```

Detailed health must include provider readiness for:

```text
email
sms
payment
```
