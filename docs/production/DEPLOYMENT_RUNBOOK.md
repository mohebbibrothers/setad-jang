# Deployment Runbook — Setad Jang

## 1. Pre-deployment gate

Every deployment must pass:

```bash
git status --short --branch
make verify
```

This includes:

```text
pip check
pip-audit
bandit
detect-secrets
ruff
Django check
deploy check
migration drift check
OpenAPI validation
pytest with coverage threshold
```

## 2. Build image

```bash
docker-compose build web worker beat
```

Production image uses:

```text
multi-stage build
wheel cache stage
tini
gosu privilege drop
readiness healthcheck
non-root runtime after entrypoint bootstrap
```

## 3. Deploy order

1. Provision/verify PostgreSQL.
2. Provision/verify Redis.
3. Configure `.env` from `ENVIRONMENT_MATRIX.md`.
4. Build and publish image.
5. Run web with `RUN_MIGRATIONS=1` exactly once per release.
6. Run collectstatic if static assets changed.
7. Start worker and beat.
8. Verify health endpoints.
9. Verify metrics endpoint.
10. Run smoke tests.

## 4. Docker compose local production-like

```bash
cp .env.example .env
# edit .env
POSTGRES_PASSWORD=<strong-password> docker-compose up --build -d
```

توپولوژی سرویس‌ها (یافتهٔ P3 ممیزیِ مستقل — «web بدون proxy»):

- `nginx` تنها نقطهٔ ورود عمومی است و روی `${NGINX_PORT:-80}` منتشر می‌شود
  (`deploy/nginx.conf`); خودِ `web` فقط روی `127.0.0.1:8000` باز است.
- nginx headerهای `X-Forwarded-For / X-Forwarded-Proto / X-Forwarded-Host`
  را می‌سازد؛ به همین دلیل `NUM_PROXIES=1` در compose ست شده است —
  **اگر توپولوژی را عوض کردی (حذف nginx، افزودن LB دوم و…)،
  `NUM_PROXIES` را دقیقاً به تعداد پراکسی‌های قابل اعتمادِ واقعی بده یا 0**
  (پیش‌فرضِ fail-closed: XFF ورودی هرگز معتبر نیست — `apps/core/client_ip.py`).
- TLS termination یا در LB بالادست انجام می‌شود یا با mount کردن cert در
  همین nginx (پورت 443 + `listen ... ssl`). settings از قبل
  `SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https")` را دارد و
  با `X-Forwarded-Proto` هماهنگ است.
- (رفع F5 ممیزی) از این فاز `deploy/nginx.conf` هدر `X-Forwarded-Proto`
  ورودی را **فقط** از شبکه‌های خصوصی (127.0.0.1، 172.16/12، 10/8، 192.168/16)
  می‌پذیرد و برای بقیه همان `$scheme`ِ خودِ کانکشن را ست می‌کند (سرریزِ
  پروتکل با map)؛ پس spoof کردنِ `https` ممکن نیست و اگر TLS را روی پروکسیِ
  host خاتمه می‌دهی، `SECURE_SSL_REDIRECT=True` هم بدون حلقه کار می‌کند.
  (XFF برای IP-گیری با منطق `NUM_PROXIES`/`client_ip.py` تنظیم می‌شود — همان
  مسیر قبلی، دست‌نخورده.)
- `web` healthcheck واقعی روی `/api/v1/health/` دارد و کارگرها/beat با
  `service_healthy` صبر می‌کنند تا مهاجرت‌های وب تمام شود (قبلاً
  `service_started` بود — یافتهٔ P3 ممیزی).

## 5. Smoke checklist

```bash
# از مسیر عمومی (پروکسی):
curl -fsS http://127.0.0.1:${NGINX_PORT:-80}/api/v1/health/
curl -fsS http://127.0.0.1:${NGINX_PORT:-80}/api/v1/health/ready/
curl -fsS http://127.0.0.1:${NGINX_PORT:-80}/api/v1/health/detailed/
curl -fsS http://127.0.0.1:${NGINX_PORT:-80}/api/v1/metrics/
# و در صورت نیاز مستقیم از web (فقط loopback):
curl -fsS http://127.0.0.1:8000/api/v1/health/
```

Manual app smoke:

```text
Auth signup/login OTP flow
Tabyin public content list
Madadkar public campaigns
LMS public courses
Kindness Wall public listings
Support Desk authenticated ticket creation
Admin dashboard access
```

## 6. Rollback

Rollback must be planned before deployment.

1. Keep previous image tag.
2. Check whether migrations are backward-compatible.
3. If migration is not reversible, restore database backup.
4. Redeploy previous image.
5. Verify health and smoke checks.

**نکتهٔ ممیزی مستقل (P3 — بازگردانیِ مهاجرت):** rollbackِ ایمیج به‌تنهایی
مهاجرت‌های اعمال‌شده را undo نمی‌کند؛ «کدِ قدیمی + اسکیمای جدید» بدترین
حالت است. اگر رلیزِ جدید مهاجرت داشته باشد:

```bash
# فهرست مهاجرت‌های رلیز جدید (ترتیب معکوس اعمال) را قبل از دیپلوی مشخص کن:
# app:مقصد — با کدِ NEW اجرا می‌شود (فایل‌های مهاجرت جدید فقط در کد جدیدند):
ROLLBACK_MIGRATIONS="lms:0004_learningactivitystatement madadkar:0007_campaigndisbursement" \
  ./update-back.sh
```

- مقدار پیش‌فرض `ROLLBACK_MIGRATIONS` خالی است و رفتار قبلی (فقط ایمیج)
  حفظ می‌شود؛ اسکریپت در حالت rollback **اول** مهاجرت‌های ذکرشده را به عقب
  برمی‌گرداند و **بعد** ایمیج را عوض می‌کند.
- اگر مهاجرت revers نبود (مثلاً حذف داده)، فقط restore از BACKUP_RESTORE_RUNBOOK.
- در هر صورت: `NUM_PROXIES` را در .env استقرار تنظیم کن (۰ یا تعداد واقعی
  پراکسی‌های قابل اعتماد) — یافتهٔ P1 ممیزی.

## 7. Post-deployment monitoring

Watch for:

```text
HTTP 5xx rate
request latency
Celery task failures
DB latency
Redis latency
SLA breach spike
payment failures
OTP delivery failures
```

Use:

```text
/api/v1/metrics/
/api/v1/health/detailed/
Flower
Sentry
structured JSON logs
```

### 7.1 Metrics scrape after the P1-2 hardening

`/api/v1/metrics/` در production پشت Bearer token است و خروجی‌اش در حالت
multiprocess (gunicorn N-worker) جمعِ همهٔ workerهاست (`PROMETHEUS_MULTIPROC_DIR`
در image ست شده؛ deploy/gunicorn.conf.py فایل‌های worker مرده را پاک می‌کند):

```bash
# scrape-config Prometheus:
#   authorization: { type: Bearer, credentials: "<PROMETHEUS_METRICS_TOKEN>" }
curl -s -H "Authorization: Bearer $(grep ^PROMETHEUS_METRICS_TOKEN= .env | cut -d= -f2)" \
  http://127.0.0.1:8000/api/v1/metrics/ | head
```

اگر توکن تنظیم‌نشده باشد endpoint عملاً 404 است — این fail-closed عمدی است.

### 7.2 External reachability verification (P1-5)

از داخل سرور (بعد از هر deploy) و یک‌بار از بیرون (DNS/TLS واقعی) تأیید شود؛
timeout از بیرون بدون پاسخ HTTP، خودش incident است:

```bash
curl -fsS -m 5 http://127.0.0.1:8000/api/v1/health/            # expected 200
curl -fsS -m 8 https://besat.me/api/v1/health/                  # expected 200 + JSON
curl -sSv -m 8 https://www.besat.me/api/v1/health/ -o /dev/null # DNS باید resolve شود
nginx -t && systemctl is-active nginx
```

چک‌لیست الزامی: health 200؛ TLS valid؛ `NUM_PROXIES=1` ست باشد (وگرنه IPها در
throttle/guard اشتباه می‌شوند)؛ `ALLOWED_HOSTS` شامل هر دامنهٔ فعال.

