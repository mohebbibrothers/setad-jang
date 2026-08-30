# Security Policy / سیاست امنیتی

(افزودنِ رفع F3 ممیزی ۲۰۲۶-۰۸-۳۰ — کانالِ رسمیِ افشا برای محققان بیرونی.)

## Reporting a vulnerability / گزارش آسیب‌پذیری

لطفاً آسیب‌پذیری‌ها را **خصوصی** گزارش دهید — نه در Issue عمومی:

- **GitHub → Security tab → «Report a vulnerability»** (private vulnerability
  reporting) — ارجح؛ این ریپو روی گیت‌هاب است و گزارش خصوصی crypto-اجباری است.
- در صورت نبودِ دسترسی: ایمیل به maintainersِ ریپو با پیشوندِ
  subject `[security]`.

تضمین‌ها:

- پاسخِ اولیه (triage) حداکثر تا ۵ روز کاری.
- در طولِ بررسی، گزارش را public نکنید؛ ما هم تا patchِ منتشرشده افشا نمی‌کنیم.
- safe harbor: گزارشِ Good-faith بدونِ دسترسی/تخریب داده، پیگرد ندارد.

## Out of scope

- آسیب‌پذیری‌های نیازمندِ دسترسیِ فیزیکی/host به سرویس‌های productionِ داخلی.
- تست‌های نفوذِ بدونِ هماهنگی (rate-limitها فعال‌اند و مسدود می‌شوید).

## Supported versions

شاخۀ `main` (پیش از برقراریِ taggingِ فراخوانی‌شده در PLAN — تا آن زمانِ
«تاریخِ کامیت» همان نسخه است).
