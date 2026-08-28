# ساختار پروژه

> این فایل **تولیدشده** است. دستی ویرایشش نکنید.
> بازتولید: `make structure` — بررسی drift در CI: `make structure-check`

نسخهٔ قبلی این سند دستی نگهداری می‌شد و کهنه شده بود: شش اپ در آن غایب
بودند و تعداد مایگریشن‌ها غلط بود. حالا از روی خود مخزن ساخته می‌شود و
یک گیت CI اختلافش با کد را می‌گیرد، پس دیگر نمی‌تواند بی‌صدا کهنه شود.

## اپلیکیشن‌ها

مجموع: **13 اپ** · 95 مدل · 54 مایگریشن · 285 ویو · 285 مسیر

| اپ | مدل | مایگریشن | ویو | مسیر |
|---|---:|---:|---:|---:|
| `activity` | 1 | 1 | 2 | 2 |
| `audit_logs` | 1 | 4 | 3 | 3 |
| `authentication` | 4 | 9 | 29 | 30 |
| `command_center` | 0 | 0 | 1 | 1 |
| `core` | 2 | 3 | 1 | 0 |
| `kindness_wall` | 12 | 2 | 34 | 34 |
| `lms` | 18 | 4 | 51 | 51 |
| `madadkar` | 14 | 8 | 47 | 47 |
| `notifications` | 4 | 3 | 7 | 7 |
| `public_reports` | 3 | 2 | 7 | 7 |
| `r4j` | 15 | 9 | 36 | 36 |
| `support_desk` | 19 | 6 | 54 | 54 |
| `tabyin` | 2 | 3 | 13 | 13 |

## قرارداد لایه‌ها

هر اپ از یک تفکیک ثابت پیروی می‌کند:

| فایل | مسئولیت |
|---|---|
| `models.py` | مدل‌های داده |
| `selectors.py` | خواندن داده (بدون side effect) |
| `services.py` | منطق کسب‌وکار و نوشتن |
| `serializers.py` | اعتبارسنجی ورودی/خروجی |
| `views.py` | لایهٔ HTTP |
| `filters.py` | فیلترهای queryset |
| `permissions.py` | کنترل دسترسی |
| `tasks.py` | تسک‌های Celery |
| `throttles.py` | محدودسازی نرخ |
| `choices.py` | مقادیر ثابت و انتخاب‌ها |
| `export.py` | خروجی اکسل |
| `urls.py` | مسیرها |

قواعدی که با تست معماری (`tests/test_architecture_discipline.py`) اجرا می‌شوند:

- هر ماژول production باید docstring سطح ماژول داشته باشد.
- `views.py` نباید مستقیماً روی manager یا queryset مدل بنویسد؛
  نوشتن از طریق لایهٔ `services.py` انجام می‌شود.
- `TODO`/`FIXME` مجاز است ولی باید شمارهٔ issue داشته باشد و از سقف
  تعیین‌شده بیشتر نشود — بدهی فنی باید ثبت شود، نه پنهان.

## درخت دایرکتوری

```text
setad-jang/
├── activity/
│   ├── migrations/
│   ├── __init__.py
│   ├── admin.py
│   ├── apps.py
│   ├── choices.py  # مقادیر ثابت و انتخاب‌ها
│   ├── filters.py  # فیلترهای queryset
│   ├── models.py  # مدل‌های داده
│   ├── permissions.py  # کنترل دسترسی
│   ├── selectors.py  # خواندن داده (بدون side effect)
│   ├── serializers.py  # اعتبارسنجی ورودی/خروجی
│   ├── services.py  # منطق کسب‌وکار و نوشتن
│   ├── tasks.py  # تسک‌های Celery
│   ├── throttles.py  # محدودسازی نرخ
│   ├── urls.py  # مسیرها
│   └── views.py  # لایهٔ HTTP
├── audit_logs/
│   ├── management/
│   ├── migrations/
│   ├── tests/
│   ├── __init__.py
│   ├── actions.py
│   ├── admin.py
│   ├── apps.py
│   ├── chain.py
│   ├── exporters.py
│   ├── filters.py  # فیلترهای queryset
│   ├── helpers.py
│   ├── models.py  # مدل‌های داده
│   ├── retention.py
│   ├── selectors.py  # خواندن داده (بدون side effect)
│   ├── serializers.py  # اعتبارسنجی ورودی/خروجی
│   ├── services.py  # منطق کسب‌وکار و نوشتن
│   ├── tasks.py  # تسک‌های Celery
│   ├── urls.py  # مسیرها
│   └── views.py  # لایهٔ HTTP
├── authentication/
│   ├── data/
│   ├── management/
│   ├── migrations/
│   ├── tests/
│   ├── __init__.py
│   ├── admin.py
│   ├── anti_abuse.py
│   ├── apps.py
│   ├── backends.py
│   ├── choices.py  # مقادیر ثابت و انتخاب‌ها
│   ├── constants.py
│   ├── deprecation.py
│   ├── filters.py  # فیلترهای queryset
│   ├── jwt_auth.py
│   ├── logging_utils.py
│   ├── managers.py
│   ├── models.py  # مدل‌های داده
│   ├── normalizers.py
│   ├── otp.py
│   ├── permissions.py  # کنترل دسترسی
│   ├── providers.py
│   ├── selectors.py  # خواندن داده (بدون side effect)
│   ├── serializers.py  # اعتبارسنجی ورودی/خروجی
│   ├── services.py  # منطق کسب‌وکار و نوشتن
│   ├── signals.py
│   ├── tasks.py  # تسک‌های Celery
│   ├── throttles.py  # محدودسازی نرخ
│   ├── urls.py  # مسیرها
│   ├── validators.py
│   └── views.py  # لایهٔ HTTP
├── command_center/
│   ├── tests/
│   ├── __init__.py
│   ├── admin.py
│   ├── apps.py
│   ├── filters.py  # فیلترهای queryset
│   ├── models.py  # مدل‌های داده
│   ├── permissions.py  # کنترل دسترسی
│   ├── selectors.py  # خواندن داده (بدون side effect)
│   ├── serializers.py  # اعتبارسنجی ورودی/خروجی
│   ├── services.py  # منطق کسب‌وکار و نوشتن
│   ├── throttles.py  # محدودسازی نرخ
│   ├── urls.py  # مسیرها
│   └── views.py  # لایهٔ HTTP
├── core/
│   ├── health/
│   ├── migrations/
│   ├── static/
│   ├── tests/
│   ├── __init__.py
│   ├── admin.py
│   ├── admin_i18n.py
│   ├── api_cache.py
│   ├── api_contracts.py
│   ├── apps.py
│   ├── cache.py
│   ├── cache_invalidation.py
│   ├── cache_policy.py
│   ├── cache_signals.py
│   ├── db_performance.py
│   ├── email_backends.py
│   ├── excel.py
│   ├── exceptions.py
│   ├── fields.py
│   ├── file_security.py
│   ├── frontend_revalidation.py
│   ├── logging.py
│   ├── managers.py
│   ├── metrics.py
│   ├── metrics_views.py
│   ├── middleware.py
│   ├── models.py  # مدل‌های داده
│   ├── observability.py
│   ├── pagination.py
│   ├── performance.py
│   ├── performance_contracts.py
│   ├── permissions.py  # کنترل دسترسی
│   ├── provider_readiness.py
│   ├── public_media.py
│   ├── responses.py
│   ├── schemas.py
│   ├── search.py
│   ├── storage.py
│   ├── tasks.py  # تسک‌های Celery
│   ├── throttling.py
│   └── views.py  # لایهٔ HTTP
├── kindness_wall/
│   ├── migrations/
│   ├── tests/
│   ├── __init__.py
│   ├── admin.py
│   ├── apps.py
│   ├── choices.py  # مقادیر ثابت و انتخاب‌ها
│   ├── export.py  # خروجی اکسل
│   ├── filters.py  # فیلترهای queryset
│   ├── managers.py
│   ├── matching.py
│   ├── models.py  # مدل‌های داده
│   ├── permissions.py  # کنترل دسترسی
│   ├── selectors.py  # خواندن داده (بدون side effect)
│   ├── serializers.py  # اعتبارسنجی ورودی/خروجی
│   ├── services.py  # منطق کسب‌وکار و نوشتن
│   ├── signals.py
│   ├── tasks.py  # تسک‌های Celery
│   ├── throttles.py  # محدودسازی نرخ
│   ├── urls.py  # مسیرها
│   ├── validators.py
│   └── views.py  # لایهٔ HTTP
├── lms/
│   ├── migrations/
│   ├── tests/
│   ├── __init__.py
│   ├── admin.py
│   ├── apps.py
│   ├── certificate.py
│   ├── choices.py  # مقادیر ثابت و انتخاب‌ها
│   ├── export.py  # خروجی اکسل
│   ├── filters.py  # فیلترهای queryset
│   ├── managers.py
│   ├── models.py  # مدل‌های داده
│   ├── permissions.py  # کنترل دسترسی
│   ├── selectors.py  # خواندن داده (بدون side effect)
│   ├── serializers.py  # اعتبارسنجی ورودی/خروجی
│   ├── services.py  # منطق کسب‌وکار و نوشتن
│   ├── signals.py
│   ├── tasks.py  # تسک‌های Celery
│   ├── throttles.py  # محدودسازی نرخ
│   ├── urls.py  # مسیرها
│   ├── validators.py
│   └── views.py  # لایهٔ HTTP
├── madadkar/
│   ├── management/
│   ├── migrations/
│   ├── payment_providers/
│   ├── tests/
│   ├── __init__.py
│   ├── admin.py
│   ├── apps.py
│   ├── choices.py  # مقادیر ثابت و انتخاب‌ها
│   ├── export.py  # خروجی اکسل
│   ├── filters.py  # فیلترهای queryset
│   ├── managers.py
│   ├── models.py  # مدل‌های داده
│   ├── permissions.py  # کنترل دسترسی
│   ├── reconciliation.py
│   ├── selectors.py  # خواندن داده (بدون side effect)
│   ├── serializers.py  # اعتبارسنجی ورودی/خروجی
│   ├── services.py  # منطق کسب‌وکار و نوشتن
│   ├── signals.py
│   ├── tasks.py  # تسک‌های Celery
│   ├── throttles.py  # محدودسازی نرخ
│   ├── urls.py  # مسیرها
│   ├── validators.py
│   └── views.py  # لایهٔ HTTP
├── notifications/
│   ├── migrations/
│   ├── tests/
│   ├── __init__.py
│   ├── admin.py
│   ├── apps.py
│   ├── choices.py  # مقادیر ثابت و انتخاب‌ها
│   ├── domain.py
│   ├── filters.py  # فیلترهای queryset
│   ├── managers.py
│   ├── models.py  # مدل‌های داده
│   ├── permissions.py  # کنترل دسترسی
│   ├── providers.py
│   ├── selectors.py  # خواندن داده (بدون side effect)
│   ├── serializers.py  # اعتبارسنجی ورودی/خروجی
│   ├── services.py  # منطق کسب‌وکار و نوشتن
│   ├── tasks.py  # تسک‌های Celery
│   ├── throttles.py  # محدودسازی نرخ
│   ├── urls.py  # مسیرها
│   └── views.py  # لایهٔ HTTP
├── public_reports/
│   ├── migrations/
│   ├── tests/
│   ├── __init__.py
│   ├── admin.py
│   ├── apps.py
│   ├── choices.py  # مقادیر ثابت و انتخاب‌ها
│   ├── filters.py  # فیلترهای queryset
│   ├── managers.py
│   ├── models.py  # مدل‌های داده
│   ├── permissions.py  # کنترل دسترسی
│   ├── selectors.py  # خواندن داده (بدون side effect)
│   ├── serializers.py  # اعتبارسنجی ورودی/خروجی
│   ├── services.py  # منطق کسب‌وکار و نوشتن
│   ├── signals.py
│   ├── test_admin_ux.py
│   ├── throttles.py  # محدودسازی نرخ
│   ├── urls.py  # مسیرها
│   ├── validators.py
│   └── views.py  # لایهٔ HTTP
├── r4j/
│   ├── migrations/
│   ├── tests/
│   ├── __init__.py
│   ├── admin.py
│   ├── apps.py
│   ├── choices.py  # مقادیر ثابت و انتخاب‌ها
│   ├── field_applicators.py
│   ├── filters.py  # فیلترهای queryset
│   ├── managers.py
│   ├── models.py  # مدل‌های داده
│   ├── permissions.py  # کنترل دسترسی
│   ├── selectors.py  # خواندن داده (بدون side effect)
│   ├── serializers.py  # اعتبارسنجی ورودی/خروجی
│   ├── services.py  # منطق کسب‌وکار و نوشتن
│   ├── signals.py
│   ├── throttles.py  # محدودسازی نرخ
│   ├── urls.py  # مسیرها
│   ├── validators.py
│   └── views.py  # لایهٔ HTTP
├── support_desk/
│   ├── migrations/
│   ├── __init__.py
│   ├── admin.py
│   ├── apps.py
│   ├── choices.py  # مقادیر ثابت و انتخاب‌ها
│   ├── export.py  # خروجی اکسل
│   ├── filters.py  # فیلترهای queryset
│   ├── managers.py
│   ├── models.py  # مدل‌های داده
│   ├── permissions.py  # کنترل دسترسی
│   ├── selectors.py  # خواندن داده (بدون side effect)
│   ├── serializers.py  # اعتبارسنجی ورودی/خروجی
│   ├── services.py  # منطق کسب‌وکار و نوشتن
│   ├── tasks.py  # تسک‌های Celery
│   ├── throttles.py  # محدودسازی نرخ
│   ├── urls.py  # مسیرها
│   ├── validators.py
│   └── views.py  # لایهٔ HTTP
└── tabyin/
    ├── management/
    ├── migrations/
    ├── providers/
    ├── sync/
    ├── tests/
    ├── __init__.py
    ├── admin.py
    ├── apps.py
    ├── choices.py  # مقادیر ثابت و انتخاب‌ها
    ├── filters.py  # فیلترهای queryset
    ├── managers.py
    ├── models.py  # مدل‌های داده
    ├── selectors.py  # خواندن داده (بدون side effect)
    ├── serializers.py  # اعتبارسنجی ورودی/خروجی
    ├── services.py  # منطق کسب‌وکار و نوشتن
    ├── tasks.py  # تسک‌های Celery
    ├── throttles.py  # محدودسازی نرخ
    ├── urls.py  # مسیرها
    └── views.py  # لایهٔ HTTP
```

## زیرساخت مشترک (`apps/core`)

```text
apps/core/
├── health/
├── migrations/
├── static/
├── tests/
├── __init__.py
├── admin.py
├── admin_i18n.py
├── api_cache.py
├── api_contracts.py
├── apps.py
├── cache.py
├── cache_invalidation.py
├── cache_policy.py
├── cache_signals.py
├── db_performance.py
├── email_backends.py
├── excel.py
├── exceptions.py
├── fields.py
├── file_security.py
├── frontend_revalidation.py
├── logging.py
├── managers.py
├── metrics.py
├── metrics_views.py
├── middleware.py
├── models.py  # مدل‌های داده
├── observability.py
├── pagination.py
├── performance.py
├── performance_contracts.py
├── permissions.py  # کنترل دسترسی
├── provider_readiness.py
├── public_media.py
├── responses.py
├── schemas.py
├── search.py
├── storage.py
├── tasks.py  # تسک‌های Celery
├── throttling.py
└── views.py  # لایهٔ HTTP
```
