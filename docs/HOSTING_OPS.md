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
                    └─ https://api.besat.me   (cPanel: index.php → 127.0.0.1:8765 → Django)
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
| بکاپ دستی (db + media) | `bash scripts/backup_daily.sh` |
| دامپِ دیتابیس با اتصالِ خودِ جنگو | `<venv>/python scripts/db_dump.py --out <file>` |
| بازبینیِ سالم‌بودنِ یک دامپ | `<venv>/python scripts/db_dump.py --verify --out <file>` |
| اعتبارنامهٔ دیتابیس (ماسک‌شده) + تست اتصال | `bash scripts/backup_daily.sh --whoami` |
| فهرستِ بکاپ‌ها | `bash scripts/backup_daily.sh --verify` |
| تستِ سلامتِ عمومی | `bash scripts/smoke_test.sh https://besat.me` |
| بازگردانیِ لایهٔ سرو (پیش‌نمایش) | `bash scripts/host_web_recover.sh` |
| بازگردانیِ لایهٔ سرو + تأیید عمومی | `bash scripts/host_web_recover.sh --apply` |
| یک‌جا: سرو + تمیز + بکاپ + cron + گزارش | `bash scripts/host_stabilize.sh` |
| دیپلویِ کد | `bash ~/deploy-back.sh` |

## کرون‌های عملیاتی

```
20 2 * * *  backup_daily.sh        # دامپِ دیتابیس + media، چرخشِ ۷ روزه
10 5 * * *  tmp/restart.txt        # ری‌استارتِ آرامِ برنامه
```

چرخشِ بکاپ عمدی است: هاستِ قبلی با **دیسکِ ۱۰۱٪** از کار افتاد. حالا حداکثر
۷ نسخه نگه داشته می‌شود و فضای آزاد در `host_doctor.sh` پایش می‌شود.

## عیب‌یابیِ سریع

| نشانه | اول چه کاری |
|---|---|
| کل `/api/v1/*` → ۵۰۰/۴۰۴ | `bash scripts/host_web_recover.sh` — زنجیرهٔ `index.php → 8765 → Django` را بازسازی و تأیید می‌کند |
| «Web application could not be started» | `DJANGO_SETTINGS_MODULE=config.settings.production <venv>/python -c "import passenger_wsgi"` — خطای واقعی را چاپ می‌کند |
| صفحه ۴۰۴ از خودِ LiteSpeed | vhost/docroot: `uapi DomainInfo single_domain_data domain=api.besat.me` |
| تصاویر ۴۰۴ ولی API سالم | `media/` خالی یا مجوزِ پوشه؛ بخش ۶ doctor |
| عددِ بازدید چند برابر می‌شود | dedupe به `X-Viewer-Id` وابسته است؛ کش/دیتابیسِ `KindnessListingView` را چک کنید |
| بکاپِ دیتابیس صفر/چند بایتی | `bash scripts/backup_daily.sh --whoami` — اعتبارنامه و `SELECT 1` را نشان می‌دهد |
| دیسک پر می‌شود | `bash scripts/host_cleanup.sh` (پیش‌نمایش) سپس `--apply --logs` |

## درس‌های مهاجرت (۲۰۲۶–۱۱)

1. **تغییرِ نامِ کاربر** (`baahamnc` → `besatme`) سه لایه را می‌شکند: `.env`،
   `virtualenv`، و `.htaccess`. همیشه بعد از مهاجرت این سه را چک کنید.
7. **Passenger روی این هاست در vhost وصل نیست.** سروِ واقعیِ production زنجیرهٔ
   `index.php → 127.0.0.1:8765 → Django` است. حذفِ `index.php` یا `stop` کردنِ سرورِ WSGI
   سایت را ۴۰۴/۵۰۲ می‌کند — شکستنِ همین زنجیره دلیلِ قطعیِ یک‌باره بود. برای همین
   `host_cleanup.sh` دیگر به `index.php`، `run/`، `logs/app.log` و `staticfiles/` دست نمی‌زند
   و `host_stabilize.sh` قبل از هر تمیزکاری، لایهٔ سرو را بازسازی و «تأیید» می‌کند.
2. **پرووایدر dotfiles را کپی نمی‌کند** — `.env` را دستی منتقل کنید.
3. **vhost تا زمانی که cPanel بازسازی نکند** ممکن است docrootِ قدیمی را بخواند؛
   شاهدِ قطعی: فایلِ موجود در docroot با `curl -H "Host: …"` هم ۴۰۴ می‌دهد.
4. **`uapi` خروجیِ YAML می‌دهد نه JSON** — grepهای مبتنی بر JSON بی‌صدا شکست می‌خورند.
5. **`manage.py` پیش‌فرض روی `development`** می‌رود؛ برای کار با دیتابیسِ واقعی
   همیشه `DJANGO_SETTINGS_MODULE=config.settings.production`.
6. **رمزِ MySQL کوتاه‌تر از ۱۶ نویسه** باعث می‌شود اپ اصلاً بوت نشود (fail-fast عمدی).
8. **اعتبارنامهٔ دیتابیس را دوباره در bash پارس نکنید.** سایت سالم بود ولی بکاپ
   `Access denied ... (using password: YES)` می‌داد، چون `.env` چند املای هم‌معنی
   (`MYSQL_*`، `DB_*`، `DATABASE_*`) دارد و پارسرِ شل «اولین تطبیق در فایل» را برمی‌داشت
   — یعنی احتمالاً مقدارِ کهنه. حالا `backup_daily.sh` مستقیم از
   `settings.DATABASES["default"]` می‌خواند (تنها منبعِ حقیقت = همان چیزی که سایت با آن
   کار می‌کند) و `.env` فقط fallback است، آن هم با اولویتِ `MYSQL_*`.
9. **کرانِ keep-alive در حالتِ پروکسی لازم است، نه «باقی‌مانده».** سرورِ WSGI یک پروسهٔ
   معمولی است؛ بدون کرانِ هر دقیقه، اولین crash یا ری‌بوت سایت را می‌خواباند. دکتر
   نبودش را حالا `[!!]` می‌دهد و وجودش را تأیید می‌کند.
10. **بکاپ نباید احرازِ هویت را بازپیاده کند.** روی همین هاست `mariadb-dump` می‌گفت
    `ERROR 1045 Access denied` در حالی که سایت با همان کاربر/پسورد دیتابیس را می‌خواند.
    کلاینتِ بیرونی چمدانِ خودش را دارد: فایلِ آپشن (`~/.my.cnf`)، اولویتِ پسورد،
    درایور و سوکتِ متفاوت. راه‌حل: `scripts/db_dump.py` دامپ را **از داخلِ جنگو** با
    همان `connection` می‌گیرد (schema + داده، gzip، سپس یک پاسِ `--verify` که تعداد
    جدول‌ها، وجودِ نشانهٔ پایان و CRC گِزیپ را چک می‌کند). CLI فقط fallback است و آن هم
    با `--no-defaults` صدا زده می‌شود تا `.my.cnf` نتواند پسوردِ کهنه تزریق کند.
    صحت با round-trip واقعی سنجیده شد: دامپ → ری‌استور در دیتابیسِ دوم →
    `CHECKSUM TABLE` هر جدول یکسان (فارسی، ایموجی، BLOB، JSON، NULL، کوتیشن، بک‌اسلش).
