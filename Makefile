# ============================================================
# Setad Jang — Developer/CI command shortcuts
# ============================================================
# این Makefile یک entrypoint واحد برای quality gates پروژه است.
# هر دستور باید هم local و هم CI-friendly باشد.

PYTHON ?= python
MANAGE := $(PYTHON) manage.py
SCHEMA_OUTPUT ?= /tmp/setad-jang-schema-check.yaml

# NOTE (۱۴۰۵): production در برابر backendهای ایمیلِ توسعه fail-fast
# می‌کند (یافتهٔ P2 ناظر بیرونی)؛ پس deploy-check هم با backend واقعی
# (smtp) اجرا می‌شود، نه backend کنسول.
PROD_CHECK_ENV := \
	ALLOWED_HOSTS=example.com \
	CACHE_BACKEND=redis \
	CORS_ALLOWED_ORIGINS=https://example.com \
	DATABASE_ENGINE=postgres \
	POSTGRES_DB=setadjang \
	POSTGRES_USER=setadjang \
	POSTGRES_PASSWORD=strong-postgres-password \
	POSTGRES_HOST=127.0.0.1 \
	POSTGRES_PORT=5432 \
	SECRET_KEY=realistic-production-secret-key-with-more-than-fifty-characters-2026 \
	SECURE_SSL_REDIRECT=True \
	EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend \
	EMAIL_HOST=localhost \
	EMAIL_PORT=1025 \
	EMAIL_USE_TLS=False

.PHONY: help install lock lock-check lint mypy format format-check structure structure-check check deploy-check migrations-check schema-check schema-update test test-postgres coverage coverage-postgres test-sqlite-vendor test-redis pip-check pip-audit bandit secrets-scan security verify verify-fast docker-up docker-down

help:
	@printf '%s\n' 'Setad Jang commands:'
	@printf '%s\n' '  make install           Install production + dev dependencies'
	@printf '%s\n' '  make lint              Run Ruff lint checks'
	@printf '%s\n' '  make format-check      Verify Ruff formatting (CI gate)'
	@printf '%s\n' '  make format            Apply Ruff formatting'
	@printf '%s\n' '  make check             Run Django system check'
	@printf '%s\n' '  make deploy-check      Run Django deployment check with safe env'
	@printf '%s\n' '  make migrations-check  Ensure migrations are up to date'
	@printf '%s\n' '  make schema-check      Validate OpenAPI schema and detect drift'
	@printf '%s\n' '  make schema-update     Regenerate committed schema.yaml'
	@printf '%s\n' '  make structure         Regenerate STRUCTURE.md'
	@printf '%s\n' '  make structure-check   Detect STRUCTURE.md drift'
	@printf '%s\n' '  make lock              Regenerate dependency lock files'
	@printf '%s\n' '  make lock-check        Detect dependency lock drift'
	@printf '%s\n' '  make test              Run full pytest suite'
	@printf '%s\n' '  make coverage          Run full pytest suite with coverage threshold'
	@printf '%s\n' '  make security          Run dependency/SAST/secrets security gate'
	@printf '%s\n' '  make verify            Run full local/CI quality gate'

install:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt -r requirements-dev.txt

lint:
	$(PYTHON) -m ruff check .

# بخش [tool.ruff.format] در pyproject.toml با دقت تنظیم شده بود ولی هیچ گیتی
# اجرایش نمی‌کرد، و نتیجه‌اش این بود که ۵۵٪ فایل‌ها با استاندارد فرمت خودِ
# پروژه همخوان نبودند. این هدف، فرمت را از «توصیه» به «قرارداد» تبدیل می‌کند.
# یافتۀ P2-6 فاز 8: درِ نوعی. کانفیقِ progressive در pyproject (باکدلاگِ
# صریحِ disable شده آنجا مستند است) — گیتِ سبزِ امروز یعنی از این به بعد
# خطایِ نوعیِ *جدید* نمی‌تواند merge شود.
mypy:
	$(PYTHON) -m mypy

format-check:
	$(PYTHON) -m ruff format --check .

format:
	$(PYTHON) -m ruff format .

check:
	$(MANAGE) check

deploy-check:
	$(PROD_CHECK_ENV) $(MANAGE) check --deploy --settings=config.settings.production

migrations-check:
	$(MANAGE) makemigrations --check --dry-run

# اعتبارسنجی به‌تنهایی کافی نیست: schema.yaml در مخزن commit می‌شود و اگر
# سریالایزری عوض شود بدون اینکه فایل بازتولید شود، CI سبز می‌ماند و اسناد
# API بی‌صدا از کد جدا می‌افتند. این هدف علاوه بر validate، خروجی تازه را با
# نسخهٔ commit‌شده diff می‌کند.
# ⚠️ چرا schema با settings توسعهٔ پیش‌فرض تولید می‌شود (نه settings جاری CI)؟
# خروجی `spectacular` به موتور دیتابیس وابسته است: bounds فیلدهای عددی از
# `connection.ops.integer_field_ranges` می‌آید (SQLite → همه int64؛
# PostgreSQL → IntegerField=int32 و SmallIntegerField=int16). اگر CI که حالا
# روی PostgreSQL تست می‌گیرد، schema را با همان env تولید کند، خروجی با
# `schema.yaml` (که روی SQLite تولید شده) فرق می‌کند و drift همیشه مثبت
# کاذب می‌شود — دقیقاً همان failure که در ران ۲۲۷ CI رخ داد. پس هم این‌جا
# و هم در `schema-update`، settings (و در نتیجه SQLite، مستقل از env ارثی)
# صریحاً پین می‌شود تا schema.yaml در هر محیطی یکسان تولید و بررسی شود.
SCHEMA_SETTINGS := config.settings.development

schema-check:
	DJANGO_SETTINGS_MODULE=$(SCHEMA_SETTINGS) $(MANAGE) spectacular --file $(SCHEMA_OUTPUT) --validate
	@diff -u schema.yaml $(SCHEMA_OUTPUT) > /dev/null 2>&1 || { \
		echo ''; \
		echo 'ERROR: schema.yaml با کد همگام نیست. «make schema-update» را اجرا و نتیجه را commit کن.'; \
		echo ''; \
		diff -u schema.yaml $(SCHEMA_OUTPUT) | head -40; \
		exit 1; \
	}

schema-update:
	DJANGO_SETTINGS_MODULE=$(SCHEMA_SETTINGS) $(MANAGE) spectacular --file schema.yaml --validate

# STRUCTURE.md یک سند تولیدشده است. قبلاً دستی commit می‌شد و کهنه شده بود؛
# حالا بازتولیدپذیر است و drift آن در CI گرفته می‌شود.
structure:
	$(PYTHON) scripts/generate_structure.py

structure-check:
	$(PYTHON) scripts/generate_structure.py --check

pip-check:
	$(PYTHON) -m pip check

lock:
	$(PYTHON) scripts/generate_locks.py

lock-check:
	$(PYTHON) scripts/generate_locks.py --check

pip-audit:
	$(PYTHON) -m pip_audit -r requirements.txt -r requirements-dev.txt --progress-spinner off

bandit:
	$(PYTHON) -m bandit -q -r apps config -x '*/migrations/*,*/tests/*,*/tests.py' -s B101,B105

secrets-scan:
	detect-secrets scan --baseline .secrets.baseline --all-files --force-use-all-plugins --exclude-files '(^\.git/|^media/|^staticfiles/|^schema\.yaml|^\.secrets\.baseline$$|^\.pytest_cache/|^\.ruff_cache/)'

security: pip-audit bandit secrets-scan

test:
	$(PYTHON) -m pytest -q

# اجرای کامل تست‌ها روی PostgreSQL — همان موتوری که production استفاده می‌کند.
# ⚠️ ست کردن DATABASE_ENGINE به‌تنهایی کافی نیست: settings توسعه/پایه
# (`config.settings.development`) پیش‌فرضِ pytest در pyproject.toml است و
# DATABASE_ENGINE را اصلاً نمی‌خواند (base.py روی SQLite قفل است). پس این‌جا
# صریحاً `config.settings.test` ست می‌شود؛ وگرنه هدف بی‌سروصدا روی SQLite
# اجرا می‌شود و ادعای «تست روی PostgreSQL» دروغ است.
# بقیهٔ متغیرهای POSTGRES_* از environment/.env خوانده می‌شوند؛ پیش‌فرض‌های
# config/settings/test.py با docker-compose و CI هماهنگ‌اند.
test-postgres:
	DJANGO_SETTINGS_MODULE=config.settings.test DATABASE_ENGINE=postgres $(PYTHON) -m pytest -q

coverage:
	$(PYTHON) -m pytest --cov=apps --cov=config --cov-report=term --cov-fail-under=82 -q

# همان coverage ولی روی PostgreSQL؛ هم‌چنین `config.settings.test` (نکتهٔ
# بالای test-postgres). در CI این هدف با موتور postgres اجرا می‌شود تا
# قفل‌های ردیفی و FTS واقعاً آزموده شوند (نه بی‌صدا حذف شوند).
coverage-postgres:
	DJANGO_SETTINGS_MODULE=config.settings.test DATABASE_ENGINE=postgres $(PYTHON) -m pytest --cov=apps --cov=config --cov-report=term --cov-fail-under=82 -q

# زیرمجموعهٔ تست‌های vendor-specific (marker=sqlite) برای گام سریع SQLite در
# CI؛ وقتی اجرای اصلی روی PostgreSQL است، این تست‌ها skip می‌شوند و این هدف
# آن‌ها را جداگانه (و صریحاً روی SQLite — در CI متغیر DATABASE_ENGINE=postgres
# از محیط ارث می‌رسد و باید بازنویسی شود) اجرا می‌کند.
test-sqlite-vendor:
	DJANGO_SETTINGS_MODULE=config.settings.test DATABASE_ENGINE=sqlite $(PYTHON) -m pytest -q -m "sqlite"

# لایۀ کش روی Redis واقعی (یافتۀ P2-7 فاز 8)؛ در CI با سرویس redis اجرا
# می‌شود. local بدونِ redis: همه skip — هرگز قرمز نمی‌شود.
test-redis:
	DJANGO_SETTINGS_MODULE=config.settings.test CACHE_BACKEND=redis REDIS_URL=redis://127.0.0.1:6379/2 $(PYTHON) -m pytest -q -m redis tests/test_cache_layer_redis_integration.py

verify-fast: lint mypy format-check check migrations-check schema-check structure-check

verify: pip-check lock-check security lint mypy format-check check deploy-check migrations-check schema-check structure-check coverage

docker-up:
	docker-compose up --build -d

docker-down:
	docker-compose down
