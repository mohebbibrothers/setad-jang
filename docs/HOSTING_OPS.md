# راهنمای عملیاتیِ هاست (cPanel / CloudLinux)

> این سند برای هر کسی است که روزی روی سرورِ بعثت کار می‌کند — از جمله خودِ ما
> شش ماه بعد. هر دستور با یک `bash scripts/…` اجرا می‌شود، نه با کپی‌کردنِ
> دستورهای طولانی در ترمینال (که در cPanel خراب می‌شوند).

## معماریِ تولید

```
کاربر
  └─ besat.me            → Vercel  (Next.js، ISR)
        └─ /api/v1/* , /admin/* , /media/* , /static/*
              └─ پراکسیِ Vercel با API_UPSTREAM_URL
                    └─ https://api.besat.me   (cPanel، Passenger + Django)
                          └─ MySQL/MariaDB  `besatme_besat`
                          └─ media/         (آپلودها، ۹۹ فایل)
```

**نکتهٔ حیاتی:** `API_UPSTREAM_URL` در Vercel → `https://api.besat.me`.
تغییرِ آن **بدونِ Redeploy اعمال نمی‌شود**.

## دامنه‌ها و DNS

| رکورد | مقدار | توضیح |
|---|---|---|
| `besat.me` A | `216.198.79.1` | Vercel — **دست نزنید** |
| `api.besat.me` A | `85.198.13.88` | سرورِ cPanel (Zone Editorِ **همین** هاست) |
| NS | `ns3/ns4.main-dns-cloud.xyz` | Zoneِ زنده روی سرورِ cPanel است |

## کلیدهای `.env` که واقعاً خوانده می‌شوند

`config/settings/production.py` این‌ها را می‌خواند:

```env
DATABASE_ENGINE=mysql
MYSQL_NAME=besatme_besat
MYSQL_USER=besatme_besat
MYSQL_PASSWORD=…            # حداقل ۱۶ نویسه، وگرنه اپ بوت نمی‌شود
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306

SECRET_KEY=…                # حداقل ۵۰ نویسه
ALLOWED_HOSTS=besat.me,www.besat.me,api.besat.me,85.198.13.88,localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=https://besat.me,https://api.besat.me,http://85.198.13.88
DEBUG=False
```

`DB_*` / `DATABASE_*` نام‌های قدیمی‌اند و فقط برای سازگاری نگه داشته می‌شوند.

## دستورهای روزمره

| کار | دستور |
|---|---|
| گزارشِ سلامتِ کامل (فقط‌خواندنی) | `bash scripts/host_doctor.sh` |
| فقط مشکلات | `bash scripts/host_doctor.sh --quiet` |
| تمیزکاری (پیش‌نمایش) | `bash scripts/host_cleanup.sh` |
| تمیزکاری (اجرا) | `bash scripts/host_cleanup.sh --apply` |
| بکاپ دستی | `bash scripts/backup_daily.sh` |
| فهرستِ بکاپ‌ها | `bash scripts/backup_daily.sh --verify` |
| تستِ سلامتِ عمومی | `bash scripts/smoke_test.sh https://besat.me` |
| یک‌جا: تمیز + بکاپ + cron + گزارش | `bash scripts/host_stabilize.sh` |
| دیپلویِ کد | `bash ~/deploy-back.sh` |

## کرون‌های عملیاتی

```
20 2 * * *  backup_daily.sh        # دامپِ دیتابیس + media، چرخشِ ۷ روزه
10 5 * * *  tmp/restart.txt        # ری‌استارتِ آرامِ Passenger
```

چرخشِ بکاپ عمدی است: هاستِ قبلی با **دیسکِ ۱۰۱٪** از کار افتاد. حالا حداکثر
۷ نسخه نگه داشته می‌شود و فضای آزاد در `host_doctor.sh` پایش می‌شود.

## عیب‌یابیِ سریع

| نشانه | اول چه کاری |
|---|---|
| کل `/api/v1/*` → ۵۰۰ | `bash scripts/host_doctor.sh` — بخش ۷ (Passenger) و ۵ (دیتابیس) |
| «Web application could not be started» | `DJANGO_SETTINGS_MODULE=config.settings.production <venv>/python -c "import passenger_wsgi"` — خطای واقعی را چاپ می‌کند |
| صفحه ۴۰۴ از خودِ LiteSpeed | vhost/docroot: `uapi DomainInfo single_domain_data domain=api.besat.me` |
| تصاویر ۴۰۴ ولی API سالم | `media/` خالی یا مجوزِ پوشه؛ بخش ۶ doctor |
| عددِ بازدید چند برابر می‌شود | dedupe به `X-Viewer-Id` وابسته است؛ کش/دیتابیسِ `KindnessListingView` را چک کنید |
| دیسک پر می‌شود | `bash scripts/host_cleanup.sh` (پیش‌نمایش) سپس `--apply --logs` |

## درس‌های مهاجرت (۲۰۲۶–۱۱)

1. **تغییرِ نامِ کاربر** (`baahamnc` → `besatme`) سه لایه را می‌شکند: `.env`،
   `virtualenv`، و `.htaccess`ِ Passenger. همیشه بعد از مهاجرت این سه را چک کنید.
2. **پرووایدر dotfiles را کپی نمی‌کند** — `.env` را دستی منتقل کنید.
3. **vhost تا زمانی که cPanel بازسازی نکند** ممکن است docrootِ قدیمی را بخواند؛
   شاهدِ قطعی: فایلِ موجود در docroot با `curl -H "Host: …"` هم ۴۰۴ می‌دهد.
4. **`uapi` خروجیِ YAML می‌دهد نه JSON** — grepهای مبتنی بر JSON بی‌صدا شکست می‌خورند.
5. **`manage.py` پیش‌فرض روی `development`** می‌رود؛ برای کار با دیتابیسِ واقعی
   همیشه `DJANGO_SETTINGS_MODULE=config.settings.production`.
6. **رمزِ MySQL کوتاه‌تر از ۱۶ نویسه** باعث می‌شود اپ اصلاً بوت نشود (fail-fast عمدی).
