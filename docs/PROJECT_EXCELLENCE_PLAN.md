# Setad Jang — Enterprise Excellence Roadmap

این سند نقشه‌ی فازبه‌فاز ارتقای پروژه به سطح production-grade/enterprise-grade را نگه می‌دارد. هر فاز فقط وقتی بسته می‌شود که verification کامل pass شود و سپس commit/push انجام گیرد.

---

## اصول غیرقابل مذاکره

1. **Zero-warning discipline** — warning در test/check/schema مجاز نیست.
2. **Service-layer mutations** — viewها mutation دیتابیس انجام نمی‌دهند.
3. **Selector-layer reads** — queryهای پیچیده و optimized در selectors متمرکز می‌شوند.
4. **Auditability** — عملیات حساس audit log دارند.
5. **Idempotency** — taskها، payment verify و callbackهای حساس idempotent هستند.
6. **Operational safety** — production config باید fail-fast و secure-by-default باشد.
7. **Documentation as architecture** — module/class/functionهای production باید docstring داشته باشند.
8. **Tests as contract** — هر اصلاح معماری با تست محافظتی همراه می‌شود.

---

## Phase 0 — Production Baseline Hardening ✅

Status: Done and pushed in commit `9043703`.

خروجی‌ها:
- PostgreSQL production config و Docker service.
- Celery queue coverage برای Madadkar.
- ZarinpalProvider واقعی.
- حذف runtime artifacts.
- sync migration drift.
- operational hardening tests.
- README/STRUCTURE refresh.

---

## Phase 1 — Architecture Discipline Hardening ✅

Status: Done in current phase.

خروجی‌ها:
- module docstring برای production modules.
- top-level class/function docstring برای production code.
- حذف `pass`/placeholder/TODO/NotImplementedError از production code.
- quality gate تستی برای جلوگیری از regression معماری.
- enforce ممنوعیت mutation مستقیم دیتابیس در viewها.

Verification gate:

```bash
ruff check .
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py spectacular --file schema.yaml --validate
pytest -q
```

---

## Phase 2 — Core API Contract & Error Handling

هدف: تبدیل core contract به یک لایه‌ی کاملاً deterministic و schema-friendly.

Scope:
- تست‌های exhaustiveness برای `custom_exception_handler`.
- contract tests برای envelope در success/error/pagination.
- schema helper hardening.
- health response contract stabilization.
- بررسی binary response exceptions مثل Excel export.

Definition of Done:
- خطاهای validation/permission/throttle/500 با تست دقیق پوشش داده شوند.
- هیچ endpointی response envelope ناسازگار نداشته باشد، مگر binary download مستندشده.

---

## Phase 3 — Authentication Security Deep Audit

هدف: adversarial hardening برای auth و OTP.

Scope:
- تست replay/race/expired/attempt-limit برای OTP.
- تست enumeration-safety برای forgot/login/signup.
- تست inactive/soft-deleted users.
- log redaction برای OTP/token/secret.
- آماده‌سازی interface تمیز برای SMS vendor واقعی.

Definition of Done:
- auth flow در برابر abuseهای رایج تست‌شده و deterministic باشد.

---

## Phase 4 — Public Reports Modernization

هدف: رساندن public_reports به استاندارد R4J/Madadkar.

Scope:
- permission matrix کامل.
- audit dispatch برای admin mutations.
- file validation tests.
- IDOR و state transition tests.
- service/selector polish.

Definition of Done:
- public_reports دیگر weak link تست و معماری نباشد.

---

## Phase 5 — Audit Logs Forensic Hardening

هدف: append-only و forensic-grade شدن audit trail.

Scope:
- read-only admin behavior.
- جلوگیری از delete/change در سطح admin/service.
- metadata completeness tests.
- async failure isolation tests.

Definition of Done:
- audit logs قابل اتکا برای trace و incident review باشند.

---

## Phase 6 — Observability & Health

هدف: آماده‌سازی runtime برای monitoring واقعی.

Scope:
- تفکیک liveness/readiness/detailed health.
- DB/Redis/cache/broker checks.
- structured logging option برای production.
- request-id propagation tests.

Definition of Done:
- health checks برای orchestrator و monitoring قابل اعتماد باشند.

---

## Phase 7 — Madadkar Financial-Grade Upgrade

هدف: رساندن payment/crowdfunding به سطح financial-grade.

Scope:
- تست‌های کامل Zarinpal HTTP edge cases.
- ledger/reconciliation طراحی و پیاده‌سازی در صورت تأیید.
- settlement/reporting hardening.
- admin financial immutability.

Definition of Done:
- پرداخت، reconciliation و گزارش مالی auditپذیر و idempotent باشند.

---

## Phase 8 — R4J Performance & Search

هدف: آمادگی برای دیتای بزرگ‌تر و search بهتر.

Scope:
- query count tests.
- PostgreSQL indexing/trigram search در صورت نیاز.
- selector optimization.
- visibility edge cases.
- bounty concurrency stress-style tests.

Definition of Done:
- endpoints اصلی R4J از نظر query و performance قابل دفاع باشند.

---

## Phase 9 — Tabyin Sync Reliability

هدف: ingestion قابل مشاهده، قابل audit و resilient.

Scope:
- SyncRun model در صورت تأیید.
- retry exhaustion tests.
- malformed payload tests.
- provider failure isolation.
- idempotency guarantees.

Definition of Done:
- sync failures قابل trace و recovery باشند.

---

## Phase 10 — CI/CD & Developer Experience ✅

هدف: هر push خودکار validate شود.

خروجی‌ها:
- GitHub Actions quality gate با PostgreSQL و Redis service containers.
- pipeline کامل: dependency check، Ruff، Django check، deploy check، migration drift، schema validation، pytest.
- Makefile به‌عنوان entrypoint واحد local/CI.
- schema artifact در CI برای review و debugging.

Definition of Done:
- main branch با quality gates خودکار محافظت می‌شود و همان دستورهای local در CI هم اجرا می‌شوند.

## Phase 11 — Phase-8 Remediation & Ops Automation ✅ (این فاز)

- امنیتی/عملیاتیِ P2: mypy gate، cache-integration روی Redis واقعی، سیاستِ رمز
  بومی، هدرهای CSP/Permissions-Policy/COOP، parity مقدارِ .env.example،
  سرویس بکاپ خودکار با verify چرخشی + WAL، دروازۀ سازگاری مایگریشن.
- بهداشت P3: آمار README، sqlite-in-volume، تاریخِ Sunset واقعی، سناریوی
  بارِ k6 (دو گسلِ حیاتی با thresholdهای هم‌راستا با Performance Contracts).

### Backlogِ صریح (پذیرفته‌شده، نه فراموش‌شده)
- **P3-19 media ثالث (hotlink-fragility):** مسیرِ پیشنهادی — پروکسیِ کش‌شونده
  در `apps/tabyin`/`apps/lms` (backendِ MediaProxy: fetch-once + ذخیره روی
  استوریج خود + rehostِ بی‌صدا با backoff؛ TTLِ ۳۰ روز برای contentِ منقضی‌شونده).
  تصمیمِ اجرا با مالک محصول چون billingِ egress دارد.
- **P3-22 schema.yaml:** commit‌شده *می‌ماند*؛ دروازۀ drift-check (schema-check)
  عمداً به فایلِ committed تکیه می‌کند و release-only‌کردنش گیتِ CI را بی‌معنی
  می‌کند. اگر دردِ diff خوانا شد: مسیرِ `make schema-update` + `.gitattributes
  linguist-generated` (بدون حذف گیت).
- **P3-21 پایتون:** CI روی 3.14 محکِ اصلی است (run سبزِ فعلی = تأیید)؛
  local 3.13 عمدی برای buildِ سریع‌تر — در ENVIRONMENT_MATRIX مستند.
- **P3-24 فرایند گیت‌هاب:** branch protection روی main (require PR + checks +
  prohibit force-push) و signed commits — تنظیماتِ ایمیج/حساب است نه کد؛
  مراحل در گزارشِ فاز ۸ (بخش «کار اپراتور») آمده.
- **تفکیک فایل‌های غول (P3-16):** الگوی اثبات‌شده در فاز ۱۱ برای بزرگ‌ترین‌ها
  (مدول‌های دامنه‌ای + facade سازگار); بقیه با همان الگو در فاز بعد — دستورِ
  کار در کامیت‌های splitِ همین فاز ثبت شده است.
